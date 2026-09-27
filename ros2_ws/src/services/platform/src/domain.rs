use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
/// 已接受任务的稳定标识。
pub struct TaskId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
/// 注册设备的稳定标识。
pub struct DeviceId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
/// 传感器的稳定标识。
pub struct SensorId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// 设备的静态描述及其关联传感器。
pub struct DeviceDescriptor {
    /// 设备标识。
    pub id: DeviceId,
    /// 面向调用者的设备名称。
    pub name: String,
    /// 该设备提供的传感器标识。
    pub sensors: Vec<SensorId>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 设备在某一时刻的健康状态快照。
pub struct DeviceState {
    /// 状态所属设备。
    pub device_id: DeviceId,
    /// 设备当前是否健康。
    pub healthy: bool,
    /// 面向调用者的状态说明。
    pub message: String,
    /// 状态更新时间，单位为 Unix epoch milliseconds。
    pub updated_at_ms: u64,
}
