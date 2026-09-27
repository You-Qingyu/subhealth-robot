//! canonical task 到 `ExecuteTask` ROS action 的类型化客户端。
//!
//! 本 crate 负责设备注册表、ROS action 映射和 executor 生命周期；业务服务只
//! 依赖 [`RosTaskClient`] 暴露的设备无关接口。

mod client;
mod config;
mod error;
mod mapper;
mod runtime;

pub use client::RosTaskClient;
pub use config::{DeviceConfig, RosRuntimeConfig, RosTaskClientConfig};
pub use error::RosTaskError;
pub use runtime::RosTaskRuntime;
