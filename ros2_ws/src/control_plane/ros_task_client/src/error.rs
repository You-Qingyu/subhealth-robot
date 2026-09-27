use thiserror::Error;

impl From<RosTaskError> for platform::ExecutionError {
    fn from(error: RosTaskError) -> Self {
        Self::Failed(error.to_string())
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
/// ROS task client 的配置、映射、通信和生命周期错误。
pub enum RosTaskError {
    /// 配置文件路径或内容无法加载。
    #[error("configuration error: {message}")]
    ConfigLoad { message: String },
    /// 配置字段不符合当前版本的约束。
    #[error("invalid configuration for {field}: {message}")]
    InvalidConfig {
        field: &'static str,
        message: String,
    },
    /// canonical task 无法映射为 ROS goal。
    #[error("invalid command for {field}: {message}")]
    InvalidCommand {
        field: &'static str,
        message: String,
    },
    /// 任务引用了未启用或未注册的设备。
    #[error("unknown device: {device_id}")]
    UnknownDevice { device_id: String },
    /// 在超时时间内没有可用的 action server。
    #[error("action server unavailable for device {device_id} at {action_name}")]
    ActionServerUnavailable {
        device_id: String,
        action_name: String,
    },
    /// ROS action server 拒绝了 goal。
    #[error("goal rejected for task {task_id}")]
    GoalRejected { task_id: String },
    /// ROS feedback/result 无法映射回 canonical 类型。
    #[error("mapping error for {field}: {message}")]
    Mapping {
        field: &'static str,
        message: String,
    },
    /// feedback 超过了会话缓冲容量。
    #[error("feedback overflow for task {task_id}: channel capacity is {capacity}")]
    FeedbackOverflow { task_id: String, capacity: usize },
    /// `rclrs` 错误无法以当前可 clone 错误类型需要的 source 形式保存。
    /// 因此在 ROS seam 保留其 Display 文本，而不是包装原始错误。
    #[error("ROS error: {0}")]
    Ros(String),
    /// ROS 内部 channel 已关闭。
    #[error("{channel} channel closed")]
    ChannelClosed { channel: &'static str },
    /// client 已进入 shutdown 状态。
    #[error("ROS task client is shutting down")]
    Shutdown,
    /// ROS executor 线程发生 panic。
    #[error("ROS executor panicked")]
    ExecutorPanicked,
}
