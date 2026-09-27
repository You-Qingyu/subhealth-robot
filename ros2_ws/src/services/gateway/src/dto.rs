use platform::{DeviceId, Primitive, Task, TaskId};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
/// HTTP 创建任务请求对应的输入模型。
pub struct CreateTask {
    /// 目标设备 ID。
    pub device_id: DeviceId,
    /// 要执行的任务原语。
    pub primitive: Primitive,
    /// 按执行顺序排列的目标。
    pub target: Vec<i32>,
    /// 可选的 Unix epoch deadline，单位为 milliseconds。
    pub deadline_ms: Option<u64>,
}

impl CreateTask {
    /// 将 HTTP 输入转换为由 Orchestration 接受的 canonical [`Task`]。
    ///
    /// 返回的任务 ID 为空，由 Repository 在创建记录时生成。
    pub fn into_task(self) -> Task {
        Task {
            id: TaskId(String::new()),
            device_id: self.device_id,
            primitive: self.primitive,
            target: self.target,
            deadline_ms: self.deadline_ms,
        }
    }
}
