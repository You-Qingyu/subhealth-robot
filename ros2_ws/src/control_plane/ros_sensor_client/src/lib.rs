//! 订阅 ROS 传感器话题的控制平面客户端。
//!
//! 本 crate 实现 [`platform::SensorProvider`]：按 `ROS_SENSOR_CONFIG` 订阅
//! 配置中的 `PhysioSample` 话题，转换为 canonical [`platform::SensorSample`]
//! 并缓存最新值。业务服务只依赖 provider 暴露的设备无关接口。

mod client;
mod config;
mod error;
mod provider;
mod runtime;

use std::sync::Arc;

pub use config::{RosSensorConfig, RosSensorRuntimeConfig, SensorConfig};
pub use error::SensorClientError;
pub use provider::RosSensorProvider;
pub use runtime::RosSensorRuntime;

/// 从 `ROS_SENSOR_CONFIG` 初始化传感器 provider 和 ROS runtime。
///
/// # 错误
///
/// 配置无效、ROS context 无法创建或 executor 无法启动时返回错误。
pub fn init() -> Result<(Arc<RosSensorProvider>, RosSensorRuntime), SensorClientError> {
    client::connect()
}
