#[derive(Debug, thiserror::Error, PartialEq, Eq)]
/// 编排层向 Gateway 暴露的业务错误。
pub enum OrchestrationError {
    /// 目标设备已有非终态任务。
    #[error("device is busy")]
    Busy,
    /// 任务或任务标识已经存在。
    #[error("task already exists")]
    Duplicate,
    /// 请求引用的任务不存在。
    #[error("task does not exist")]
    UnknownTask,
    /// 任务已经处于终态，不能再次更新。
    #[error("task is already terminal")]
    TerminalTask,
    /// 任务没有有效目标。
    #[error("task target must not be empty")]
    InvalidTarget,
    /// Repository 发生内部存储错误。
    #[error("task repository error: {0}")]
    Repository(String),
    /// 执行端拒绝任务或执行失败。
    #[error("execution port error: {0}")]
    Execution(String),
}
