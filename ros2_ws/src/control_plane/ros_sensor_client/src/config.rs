use std::{collections::HashSet, env, fs, path::Path};

use serde::Deserialize;

use crate::SensorClientError;

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
/// ROS 传感器客户端的完整 YAML 配置。
pub struct RosSensorConfig {
    /// 配置格式版本，当前必须为 `1`。
    pub version: u32,
    /// ROS 节点运行时配置。
    pub ros: RosSensorRuntimeConfig,
    /// 需要订阅的传感器清单。
    pub sensors: Vec<SensorConfig>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
/// ROS 节点运行时配置。
pub struct RosSensorRuntimeConfig {
    /// ROS node 名称。
    pub node_name: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
/// 单个传感器的静态订阅信息。
pub struct SensorConfig {
    /// 传感器 ID，对应查询接口中的 `SensorId`。
    pub id: String,
    /// 传感器采样的绝对 ROS topic 名称。
    pub topic: String,
    /// 传感器类型，例如 `spo2`。
    pub kind: String,
    /// 传感器值的可选单位。
    pub unit: Option<String>,
}

impl RosSensorConfig {
    /// 从 `ROS_SENSOR_CONFIG` 指定的路径加载并校验配置。
    ///
    /// # 错误
    ///
    /// 环境变量缺失、文件无法读取、YAML 无法解析或配置校验失败时返回错误。
    pub fn from_environment() -> Result<Self, SensorClientError> {
        let path =
            env::var_os("ROS_SENSOR_CONFIG").ok_or_else(|| SensorClientError::ConfigLoad {
                message: "ROS_SENSOR_CONFIG is not set".into(),
            })?;
        Self::from_path(Path::new(&path))
    }

    /// 从 YAML 文件加载并校验配置。
    pub fn from_path(path: &Path) -> Result<Self, SensorClientError> {
        let contents = fs::read_to_string(path).map_err(|error| SensorClientError::ConfigLoad {
            message: format!("could not read {}: {error}", path.display()),
        })?;
        let config: RosSensorConfig =
            serde_yaml::from_str(&contents).map_err(|error| SensorClientError::ConfigLoad {
                message: format!("could not parse {}: {error}", path.display()),
            })?;
        config.validate()?;
        Ok(config)
    }

    /// 校验版本、节点名以及传感器 ID 和 topic 的唯一性。
    fn validate(&self) -> Result<(), SensorClientError> {
        if self.version != 1 {
            return Err(invalid("version", "must be 1"));
        }
        if self.ros.node_name.trim().is_empty() {
            return Err(invalid("ros.node_name", "must not be empty"));
        }
        if self.sensors.is_empty() {
            return Err(invalid("sensors", "must list at least one sensor"));
        }
        let mut ids = HashSet::new();
        let mut topics = HashSet::new();
        for sensor in &self.sensors {
            validate_sensor(sensor, &mut ids, &mut topics)?;
        }
        Ok(())
    }
}

fn validate_sensor(
    sensor: &SensorConfig,
    ids: &mut HashSet<String>,
    topics: &mut HashSet<String>,
) -> Result<(), SensorClientError> {
    if sensor.id.trim().is_empty() {
        return Err(invalid("sensors.id", "must not be empty"));
    }
    if sensor.kind.trim().is_empty() {
        return Err(invalid("sensors.kind", "must not be empty"));
    }
    if !sensor.topic.starts_with('/') {
        return Err(invalid(
            "sensors.topic",
            "must be an absolute ROS topic name",
        ));
    }
    if !ids.insert(sensor.id.clone()) {
        return Err(invalid("sensors.id", "must be unique"));
    }
    if !topics.insert(sensor.topic.clone()) {
        return Err(invalid("sensors.topic", "must be unique"));
    }
    Ok(())
}

fn invalid(field: &'static str, message: &str) -> SensorClientError {
    SensorClientError::InvalidConfig {
        field,
        message: message.into(),
    }
}
