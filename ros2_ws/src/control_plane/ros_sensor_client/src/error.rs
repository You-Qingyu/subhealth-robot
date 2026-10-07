use thiserror::Error;

#[derive(Debug, Error, Clone, PartialEq, Eq)]
/// ROS 传感器客户端的配置、通信和生命周期错误。
pub enum SensorClientError {
    /// 配置文件路径或内容无法加载。
    #[error("configuration error: {message}")]
    ConfigLoad { message: String },
    /// 配置字段不符合当前版本的约束。
    #[error("invalid configuration for {field}: {message}")]
    InvalidConfig {
        field: &'static str,
        message: String,
    },
    /// `rclrs` 错误以 Display 文本保留，而不是包装原始错误。
    #[error("ROS error: {0}")]
    Ros(String),
    /// ROS executor 线程发生 panic。
    #[error("ROS sensor executor panicked")]
    ExecutorPanicked,
}
