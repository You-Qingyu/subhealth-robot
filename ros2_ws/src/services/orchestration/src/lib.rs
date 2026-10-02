//! 任务提交、执行启动和任务状态更新的编排模块。
//!
//! 编排层依赖 [`ExecutionPort`] 和 [`platform::TaskRepository`]，不依赖 ROS
//! generated type 或具体设备实现。

use platform::{
    ExecutionError, ExecutionFeedback, ExecutionResult, ExecutionSession, Task, TaskRecord,
    TaskRepository, TaskRepositoryError,
};
use std::sync::Arc;
use std::{future::Future, pin::Pin};

mod error;
mod pathfinding;

pub use error::OrchestrationError;
pub use pathfinding::{Path, PathfindingError};

/// 编排层使用的设备无关执行接口。
///
/// [`Self::validate`] 和 [`Self::execute`] 由具体执行服务实现；编排层只依赖
/// 这两个操作，不知道执行端使用的 transport 或设备协议。
pub trait ExecutionPort: Send + Sync {
    /// 检查任务是否能被执行端接受。
    fn validate<'a>(
        &'a self,
        task: &'a Task,
    ) -> Pin<Box<dyn Future<Output = Result<(), ExecutionError>> + Send + 'a>>;

    /// 启动任务并返回其 feedback 与终态结果会话。
    fn execute(
        &self,
        task: Task,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionSession, ExecutionError>> + Send + '_>>;
}

/// 协调 [`ExecutionPort`] 和 [`platform::TaskRepository`] 的任务编排器。
pub struct Orchestrator {
    execution: Arc<dyn ExecutionPort>,
    repository: Arc<dyn TaskRepository>,
    map: map::MapData,
}

impl Orchestrator {
    /// 创建一个使用指定执行端、任务 Repository 和已校验地图的编排器。
    ///
    /// 拒绝包含重复节点、悬空边、重复名称或不支持版本的地图。
    pub fn new(
        execution: Arc<dyn ExecutionPort>,
        repository: Arc<dyn TaskRepository>,
        map: map::MapData,
    ) -> Result<Self, OrchestrationError> {
        map.validate()?;
        Ok(Self {
            execution,
            repository,
            map,
        })
    }

    /// 按地图名称解析目标节点。
    pub fn resolve_target(&self, name: &str) -> Result<map::NodeId, map::MapError> {
        self.map.node_by_name(name)
    }

    /// 规划两个命名地图目标之间的最小代价路径。
    pub fn shortest_path(&self, from: &str, to: &str) -> Result<Path, OrchestrationError> {
        let start = self.resolve_target(from)?;
        let goal = self.resolve_target(to)?;
        Ok(pathfinding::shortest_path(&self.map, start, goal)?)
    }

    /// 验证、创建并启动一个任务。
    ///
    /// 调用顺序固定为：补全目标路线、执行端验证、Repository 创建记录、执行端启动任务。
    /// 目标路线中的每一对相邻 Tag 都会替换为地图上的最短路径；相邻路径的连接点不会重复。
    /// 如果任务已经创建但执行启动失败，编排器会尝试将任务写入失败终态。
    ///
    /// # 错误
    ///
    /// 目标为空、目标不在地图上或目标之间不可达时，不会创建任务；其他错误来自执行端或
    /// [`platform::TaskRepository`]。
    pub async fn submit(
        &self,
        task: Task,
    ) -> Result<(TaskRecord, ExecutionSession), OrchestrationError> {
        let target = expand_target_route(&self.map, &task.target)?;
        let task = Task { target, ..task };
        self.execution
            .validate(&task)
            .await
            .map_err(|error| OrchestrationError::Execution(error.to_string()))?;
        let record = self
            .repository
            .create_task(
                task.device_id,
                task.primitive,
                task.target,
                task.deadline_ms,
            )
            .map_err(OrchestrationError::from)?;
        let session =
            self.execution
                .execute(record.task.clone())
                .await
                .map_err(|error| {
                    match self.repository.apply_result(ExecutionResult {
                        task_id: record.task.id.clone(),
                        state: "failed".into(),
                    }) {
                        Err(repository_error) => OrchestrationError::from(repository_error),
                        Ok(_) => OrchestrationError::Execution(error.to_string()),
                    }
                })?;
        Ok((record, session))
    }

    /// 将执行反馈应用到任务记录。
    ///
    /// Repository 负责校验任务是否存在、是否已经终止以及如何更新进度。
    pub fn feedback(&self, feedback: ExecutionFeedback) -> Result<TaskRecord, OrchestrationError> {
        let record = self
            .repository
            .apply_feedback(feedback)
            .map_err(OrchestrationError::from)?;
        Ok(record)
    }

    /// 将执行终态结果应用到任务记录。
    pub fn complete(&self, result: ExecutionResult) -> Result<TaskRecord, OrchestrationError> {
        let record = self
            .repository
            .apply_result(result)
            .map_err(OrchestrationError::from)?;
        Ok(record)
    }
}

fn expand_target_route(
    map: &map::MapData,
    targets: &[i32],
) -> Result<Vec<i32>, OrchestrationError> {
    let first = *targets.first().ok_or(OrchestrationError::InvalidTarget)?;
    let first_node = node_id_for_target(first)?;
    let mut route = vec![first];

    if targets.len() == 1 {
        pathfinding::shortest_path(map, first_node, first_node)?;
        return Ok(route);
    }

    for pair in targets.windows(2) {
        let start = node_id_for_target(pair[0])?;
        let goal = node_id_for_target(pair[1])?;
        let path = pathfinding::shortest_path(map, start, goal)?;
        append_path(&mut route, path.nodes)?;
    }

    Ok(route)
}

fn node_id_for_target(target: i32) -> Result<map::NodeId, OrchestrationError> {
    u32::try_from(target)
        .map(map::NodeId)
        .map_err(|_| OrchestrationError::InvalidTarget)
}

fn append_path(route: &mut Vec<i32>, nodes: Vec<map::NodeId>) -> Result<(), OrchestrationError> {
    for node in nodes.into_iter().skip(1) {
        route.push(i32::try_from(node.0).map_err(|_| OrchestrationError::InvalidTarget)?);
    }
    Ok(())
}

impl From<map::MapError> for OrchestrationError {
    fn from(error: map::MapError) -> Self {
        Self::Map(error.to_string())
    }
}

impl From<PathfindingError> for OrchestrationError {
    fn from(error: PathfindingError) -> Self {
        Self::Pathfinding(error)
    }
}

impl From<TaskRepositoryError> for OrchestrationError {
    fn from(error: TaskRepositoryError) -> Self {
        match error {
            TaskRepositoryError::DuplicateTask => Self::Duplicate,
            TaskRepositoryError::BusyDevice => Self::Busy,
            TaskRepositoryError::UnknownTask => Self::UnknownTask,
            TaskRepositoryError::TerminalTask => Self::TerminalTask,
            TaskRepositoryError::InvalidTarget => Self::InvalidTarget,
            TaskRepositoryError::Storage(error) => Self::Repository(error),
        }
    }
}
