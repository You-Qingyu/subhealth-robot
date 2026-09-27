use crate::domain::{DeviceId, TaskId};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
/// 当前平台支持的任务原语。
pub enum Primitive {
    /// 按给定顺序执行 AprilTag 目标。
    GoToTag,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
/// 任务记录的生命周期状态。
pub enum TaskState {
    /// 已由 Repository 接受，尚未收到执行反馈。
    Accepted,
    /// 已收到执行反馈，任务仍在运行。
    Running,
    /// 执行成功并进入终态。
    Succeeded,
    /// 执行失败并进入终态。
    Failed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 发送给执行层的 canonical 任务请求。
pub struct Task {
    /// 任务标识；创建时由 Repository 生成。
    pub id: TaskId,
    /// 目标设备。
    pub device_id: DeviceId,
    /// 要执行的任务原语。
    pub primitive: Primitive,
    /// 按执行顺序排列的目标标识。
    pub target: Vec<i32>,
    /// 可选的 Unix epoch deadline，单位为 milliseconds。
    pub deadline_ms: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 任务请求及其当前执行状态的完整记录。
pub struct TaskRecord {
    /// 原始 canonical 任务。
    pub task: Task,
    /// 当前生命周期状态。
    pub state: TaskState,
    /// 当前进度，Repository 会将有限值限制在 `0.0..=1.0`。
    pub progress: f32,
    /// 当前执行阶段的描述。
    pub phase: String,
}
