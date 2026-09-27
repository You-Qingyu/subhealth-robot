use std::{collections::HashSet, env, fs, path::Path};

use crate::RosTaskError;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
/// ROS task client 的完整 YAML 配置。
pub struct RosTaskClientConfig {
    /// 配置格式版本，当前必须为 `1`。
    pub version: u32,
    /// ROS executor 和反馈缓冲区配置。
    pub ros: RosRuntimeConfig,
    /// 设备 ID 到 ROS action 名称的注册表。
    pub devices: Vec<DeviceConfig>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
/// ROS 节点运行时配置。
pub struct RosRuntimeConfig {
    /// ROS node 名称。
    pub node_name: String,
    /// 每个执行会话的 feedback 缓冲容量。
    pub feedback_buffer: usize,
    /// 等待 action server 和 goal 接受的超时时间，单位为 milliseconds。
    pub server_wait_timeout_ms: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
/// 一个可执行设备的静态注册信息。
pub struct DeviceConfig {
    /// 任务使用的设备 ID。
    pub id: String,
    /// 设备对应的绝对 ROS action 名称。
    pub action_name: String,
    /// 是否将该设备加入运行时 registry。
    pub enabled: bool,
}

impl RosTaskClientConfig {
    /// 从 `ROS_TASK_CLIENT_CONFIG` 指定的路径加载并校验配置。
    ///
    /// # 错误
    ///
    /// 环境变量缺失、文件无法读取、YAML 无法解析或配置校验失败时返回错误。
    pub fn from_environment() -> Result<Self, RosTaskError> {
        let path =
            env::var_os("ROS_TASK_CLIENT_CONFIG").ok_or_else(|| RosTaskError::ConfigLoad {
                message: "ROS_TASK_CLIENT_CONFIG is not set".into(),
            })?;
        Self::from_path(Path::new(&path))
    }

    /// 从 YAML 文件加载并校验配置。
    pub fn from_path(path: &Path) -> Result<Self, RosTaskError> {
        let contents = fs::read_to_string(path).map_err(|error| RosTaskError::ConfigLoad {
            message: format!("could not read {}: {error}", path.display()),
        })?;
        let config: RosTaskClientConfig =
            serde_yaml::from_str(&contents).map_err(|error| RosTaskError::ConfigLoad {
                message: format!("could not parse {}: {error}", path.display()),
            })?;
        config.validate()?;
        Ok(config)
    }

    /// 校验版本、运行时参数以及设备和 action 名称的唯一性。
    pub fn validate(&self) -> Result<(), RosTaskError> {
        if self.version != 1 {
            return Err(RosTaskError::InvalidConfig {
                field: "version",
                message: "must be 1".into(),
            });
        }
        validate_name("node_name", &self.ros.node_name)?;
        if self.ros.feedback_buffer == 0 {
            return Err(RosTaskError::InvalidConfig {
                field: "feedback_buffer",
                message: "must be greater than zero".into(),
            });
        }
        if self.ros.server_wait_timeout_ms == 0 {
            return Err(RosTaskError::InvalidConfig {
                field: "server_wait_timeout_ms",
                message: "must be greater than zero".into(),
            });
        }

        let mut device_ids = HashSet::new();
        let mut action_names = HashSet::new();
        for device in &self.devices {
            validate_name("device_id", &device.id)?;
            validate_name("action_name", &device.action_name)?;
            if !is_canonical_absolute_ros_name(&device.action_name) {
                return Err(RosTaskError::InvalidConfig {
                    field: "action_name",
                    message: "must be a canonical absolute ROS action name".into(),
                });
            }
            if !device_ids.insert(device.id.as_str()) {
                return Err(RosTaskError::InvalidConfig {
                    field: "device_id",
                    message: format!("duplicate device ID `{}`", device.id),
                });
            }
            if !action_names.insert(device.action_name.as_str()) {
                return Err(RosTaskError::InvalidConfig {
                    field: "action_name",
                    message: format!("duplicate action name `{}`", device.action_name),
                });
            }
        }
        Ok(())
    }
}

fn is_canonical_absolute_ros_name(value: &str) -> bool {
    value.starts_with('/')
        && value != "/"
        && value
            .strip_prefix('/')
            .is_some_and(|name| name.split('/').all(is_valid_ros_name_token))
}

fn is_valid_ros_name_token(token: &str) -> bool {
    let mut characters = token.chars();
    matches!(
        characters.next(),
        Some(character) if character.is_ascii_alphabetic() || character == '_'
    ) && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn validate_name(field: &'static str, value: &str) -> Result<(), RosTaskError> {
    if value.is_empty() {
        return Err(RosTaskError::InvalidConfig {
            field,
            message: "must not be empty".into(),
        });
    }
    if value.trim() != value {
        return Err(RosTaskError::InvalidConfig {
            field,
            message: "must not have leading or trailing whitespace".into(),
        });
    }
    Ok(())
}
