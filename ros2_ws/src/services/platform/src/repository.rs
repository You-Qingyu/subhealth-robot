use crate::execution::{ExecutionFeedback, ExecutionResult};
use crate::task::{Primitive, TaskRecord};
use crate::{DeviceId, TaskId};

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
/// Repository 操作的业务错误。
pub enum TaskRepositoryError {
    /// 生成的任务标识已经存在。
    #[error("task already exists")]
    DuplicateTask,
    /// 目标设备已有非终态任务。
    #[error("device is busy")]
    BusyDevice,
    /// 请求的任务不存在。
    #[error("task does not exist")]
    UnknownTask,
    /// 任务已经处于 `Succeeded` 或 `Failed` 终态。
    #[error("task is already terminal")]
    TerminalTask,
    /// 任务目标不符合当前原语的要求。
    #[error("task target is invalid")]
    InvalidTarget,
    /// Repository 的底层存储操作失败。
    #[error("task storage failed: {0}")]
    Storage(String),
}

/// 已接受任务及其状态转换的唯一真相源。
///
/// 每个操作从调用者视角都是原子的。实现必须保留终态记录，同时只将非终态
/// 记录视为占用设备。
pub trait TaskRepository: Send + Sync {
    /// 创建一个处于 [`TaskState::Accepted`] 的任务记录。
    ///
    /// 实现负责生成任务 ID，并在设备已有活动任务或 target 无效时返回错误。
    fn create_task(
        &self,
        device_id: DeviceId,
        primitive: Primitive,
        target: Vec<i32>,
        deadline_ms: Option<u64>,
    ) -> Result<TaskRecord, TaskRepositoryError>;

    /// 读取指定任务的完整记录。
    fn get_task(&self, task_id: &TaskId) -> Result<TaskRecord, TaskRepositoryError>;

    /// 返回当前 Repository 中保存的全部任务记录。
    fn list_tasks(&self) -> Result<Vec<TaskRecord>, TaskRepositoryError>;

    /// 原子地应用一次执行反馈，并将任务推进到 `Running`。
    fn apply_feedback(
        &self,
        feedback: ExecutionFeedback,
    ) -> Result<TaskRecord, TaskRepositoryError>;

    /// 原子地应用执行终态结果。
    ///
    /// 结果状态为 `"succeeded"` 时进入 [`TaskState::Succeeded`]，其他状态进入
    /// [`TaskState::Failed`]。
    fn apply_result(&self, result: ExecutionResult) -> Result<TaskRecord, TaskRepositoryError>;
}
