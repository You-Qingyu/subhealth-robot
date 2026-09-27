//! 内存中的 [`platform::TaskRepository`] 实现。
//!
//! 该 crate 用于当前控制平面运行时和开发验证；它不提供跨进程持久化。

use platform::{
    DeviceId, ExecutionFeedback, ExecutionResult, Primitive, TaskId, TaskRecord, TaskRepository,
    TaskRepositoryError, TaskState,
};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};

struct RepositoryState {
    records: RwLock<HashMap<TaskId, TaskRecord>>,
    next_id: AtomicU64,
}

#[derive(Clone)]
pub struct InMemoryTaskRepository {
    state: Arc<RepositoryState>,
}

impl InMemoryTaskRepository {
    /// 创建一个空的 Repository，任务 ID 从 `task-1` 开始生成。
    pub fn new() -> Self {
        Self {
            state: Arc::new(RepositoryState {
                records: RwLock::new(HashMap::new()),
                next_id: AtomicU64::new(1),
            }),
        }
    }

    fn next_task_id(&self) -> TaskId {
        TaskId(format!(
            "task-{}",
            self.state.next_id.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn is_device_busy(records: &HashMap<TaskId, TaskRecord>, device_id: &DeviceId) -> bool {
        records.values().any(|record| {
            record.task.device_id == *device_id
                && !matches!(record.state, TaskState::Succeeded | TaskState::Failed)
        })
    }
}

impl Default for InMemoryTaskRepository {
    fn default() -> Self {
        Self::new()
    }
}

impl TaskRepository for InMemoryTaskRepository {
    fn create_task(
        &self,
        device_id: DeviceId,
        primitive: Primitive,
        target: Vec<i32>,
        deadline_ms: Option<u64>,
    ) -> Result<TaskRecord, TaskRepositoryError> {
        let mut records = self
            .state
            .records
            .write()
            .map_err(|error| TaskRepositoryError::Storage(error.to_string()))?;
        if target.is_empty() {
            return Err(TaskRepositoryError::InvalidTarget);
        }
        if Self::is_device_busy(&records, &device_id) {
            return Err(TaskRepositoryError::BusyDevice);
        }

        let task_id = self.next_task_id();
        if records.contains_key(&task_id) {
            return Err(TaskRepositoryError::DuplicateTask);
        }
        let record = TaskRecord {
            task: platform::Task {
                id: task_id.clone(),
                device_id,
                primitive,
                target,
                deadline_ms,
            },
            state: TaskState::Accepted,
            progress: 0.0,
            phase: "accepted".into(),
        };
        records.insert(task_id, record.clone());
        Ok(record)
    }

    fn get_task(&self, task_id: &TaskId) -> Result<TaskRecord, TaskRepositoryError> {
        let records = self
            .state
            .records
            .read()
            .map_err(|error| TaskRepositoryError::Storage(error.to_string()))?;
        records
            .get(task_id)
            .cloned()
            .ok_or(TaskRepositoryError::UnknownTask)
    }

    fn list_tasks(&self) -> Result<Vec<TaskRecord>, TaskRepositoryError> {
        let records = self
            .state
            .records
            .read()
            .map_err(|error| TaskRepositoryError::Storage(error.to_string()))?;
        Ok(records.values().cloned().collect())
    }

    fn apply_feedback(
        &self,
        feedback: ExecutionFeedback,
    ) -> Result<TaskRecord, TaskRepositoryError> {
        let mut records = self
            .state
            .records
            .write()
            .map_err(|error| TaskRepositoryError::Storage(error.to_string()))?;
        let record = records
            .get_mut(&feedback.task_id)
            .ok_or(TaskRepositoryError::UnknownTask)?;
        if matches!(record.state, TaskState::Succeeded | TaskState::Failed) {
            return Err(TaskRepositoryError::TerminalTask);
        }
        record.state = TaskState::Running;
        record.progress = if feedback.progress.is_finite() {
            feedback.progress.clamp(0.0, 1.0)
        } else {
            0.0
        };
        record.phase = feedback.phase;
        Ok(record.clone())
    }

    fn apply_result(&self, result: ExecutionResult) -> Result<TaskRecord, TaskRepositoryError> {
        let mut records = self
            .state
            .records
            .write()
            .map_err(|error| TaskRepositoryError::Storage(error.to_string()))?;
        let record = records
            .get_mut(&result.task_id)
            .ok_or(TaskRepositoryError::UnknownTask)?;
        if matches!(record.state, TaskState::Succeeded | TaskState::Failed) {
            return Err(TaskRepositoryError::TerminalTask);
        }
        record.state = if result.state == "succeeded" {
            TaskState::Succeeded
        } else {
            TaskState::Failed
        };
        Ok(record.clone())
    }
}
