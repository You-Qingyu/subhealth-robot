use crate::domain::TaskId;
use futures_core::Stream;
use serde::{Deserialize, Serialize};
use std::future::Future;
use std::pin::Pin;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 执行过程中的增量状态。
pub struct ExecutionFeedback {
    /// 反馈所属任务。
    pub task_id: TaskId,
    /// 执行进度，业务层将其解释为 `0.0..=1.0`。
    pub progress: f32,
    /// 当前执行阶段。
    pub phase: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 一次执行的终态结果。
pub struct ExecutionResult {
    /// 结果所属任务。
    pub task_id: TaskId,
    /// 结果状态字符串；Repository 将 `"succeeded"` 映射为成功，其余值映射为失败。
    pub state: String,
}

/// 执行过程中的反馈流。
pub type ExecutionFeedbackStream =
    Pin<Box<dyn Stream<Item = Result<ExecutionFeedback, ExecutionError>> + Send>>;
/// 等待执行终态结果的 future。
pub type ExecutionResultFuture =
    Pin<Box<dyn Future<Output = Result<ExecutionResult, ExecutionError>> + Send>>;

/// 将一次执行的反馈和终态结果绑定在一起。
///
/// 调用者应持续消费 [`Self::feedback`]，并在反馈流结束后等待 [`Self::result`]。
pub struct ExecutionSession {
    /// 执行期间产生的反馈。
    pub feedback: ExecutionFeedbackStream,
    /// 执行结束时产生的结果。
    pub result: ExecutionResultFuture,
}

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
/// 执行过程中的错误。
pub enum ExecutionError {
    /// 执行端报告失败或无法继续执行。
    #[error("execution failed: {0}")]
    Failed(String),
}
