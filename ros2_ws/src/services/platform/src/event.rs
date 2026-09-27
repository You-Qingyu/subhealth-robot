use crate::domain::{DeviceId, TaskId};
use crate::task::TaskState;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
/// Gateway 对外发布事件时使用的递增序号。
pub struct EventSequence(pub u64);

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 控制平面向订阅者发送的状态变化通知。
///
/// 事件是瞬时通知，不是任务状态的第二份真相源。
pub enum SystemEvent {
    /// 任务状态发生变化。
    TaskStateChanged { task_id: TaskId, state: TaskState },
    /// 设备健康状态发生变化。
    DeviceStateChanged { device_id: DeviceId, healthy: bool },
    /// 传感器产生新数据。
    SensorUpdated { sensor_id: String },
}
