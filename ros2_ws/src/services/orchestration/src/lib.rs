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

pub use error::OrchestrationError;

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
}

impl Orchestrator {
    /// 创建一个使用指定执行端和任务 Repository 的编排器。
    pub fn new(execution: Arc<dyn ExecutionPort>, repository: Arc<dyn TaskRepository>) -> Self {
        Self {
            execution,
            repository,
        }
    }

    /// 验证、创建并启动一个任务。
    ///
    /// 调用顺序固定为：执行端验证、Repository 创建记录、执行端启动任务。
    /// 如果任务已经创建但执行启动失败，编排器会尝试将任务写入失败终态。
    ///
    /// # 错误
    ///
    /// 返回执行端或 [`platform::TaskRepository`] 的业务错误。
    pub async fn submit(
        &self,
        task: Task,
    ) -> Result<(TaskRecord, ExecutionSession), OrchestrationError> {
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
