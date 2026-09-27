use crate::domain::SensorId;
use futures_core::Stream;
use serde::{Deserialize, Serialize};
use std::pin::Pin;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// 传感器的静态描述。
pub struct SensorDescriptor {
    /// 传感器标识。
    pub id: SensorId,
    /// 传感器类型。
    pub kind: String,
    /// 传感器值的可选单位。
    pub unit: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
/// 一次传感器采样。
pub struct SensorSample {
    /// 采样来源。
    pub sensor_id: SensorId,
    /// 采样值；具体结构由传感器类型决定。
    pub value: serde_json::Value,
    /// 采样时间，单位为 Unix epoch milliseconds。
    pub timestamp_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
/// 传感器订阅筛选条件。
pub struct SensorFilter {
    /// 订阅的传感器标识集合。
    pub ids: Vec<SensorId>,
}

/// 传感器采样流。
pub type SensorStream = Pin<Box<dyn Stream<Item = SensorSample> + Send>>;

/// 采集、查询并发布传感器数据的 provider 接口。
///
/// Provider 不负责任务决策或动作执行。
pub trait SensorProvider: Send + Sync {
    /// 返回 provider 提供的传感器描述。
    fn descriptors(&self) -> Vec<SensorDescriptor>;
    /// 返回指定传感器的最新采样；传感器不存在或没有采样时返回 `None`。
    fn latest(&self, id: &SensorId) -> Option<SensorSample>;
    /// 按筛选条件订阅传感器采样。
    fn subscribe(&self, filter: SensorFilter) -> SensorStream;
}
