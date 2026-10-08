use std::{
    collections::HashMap,
    sync::{Arc, Mutex, PoisonError},
};

use futures_util::stream;
use platform::{
    SensorDescriptor, SensorFilter, SensorId, SensorProvider, SensorSample, SensorStream,
};
use ros_env::physio_interfaces::msg::PhysioSample;
use serde_json::Value;

use crate::SensorConfig;

/// provider 内部共享的最新值缓存。
pub(crate) type SampleSink = Arc<Mutex<HashMap<SensorId, SensorSample>>>;

/// 订阅 ROS 传感器话题并缓存最新采样的 provider。
///
/// Provider 只负责采集和缓存，不负责任务决策或动作执行。
pub struct RosSensorProvider {
    descriptors: Vec<SensorDescriptor>,
    samples: SampleSink,
}

impl RosSensorProvider {
    pub(crate) fn new(descriptors: Vec<SensorDescriptor>, samples: SampleSink) -> Self {
        Self {
            descriptors,
            samples,
        }
    }
}

impl SensorProvider for RosSensorProvider {
    fn descriptors(&self) -> Vec<SensorDescriptor> {
        self.descriptors.clone()
    }

    fn latest(&self, id: &SensorId) -> Option<SensorSample> {
        self.samples
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .get(id)
            .cloned()
    }

    fn subscribe(&self, _filter: SensorFilter) -> SensorStream {
        // 采样流尚未接线；接口按现有设计保留，见 docs/interfaces/sensor.md。
        Box::pin(stream::empty())
    }
}

/// 从配置构建静态传感器描述。
pub(crate) fn descriptors_from(sensors: &[SensorConfig]) -> Vec<SensorDescriptor> {
    sensors
        .iter()
        .map(|sensor| SensorDescriptor {
            id: SensorId(sensor.id.clone()),
            kind: sensor.kind.clone(),
            unit: sensor.unit.clone(),
        })
        .collect()
}

/// 将一条 ROS 采样写入共享缓存；`valid=false` 的样本被丢弃。
pub(crate) fn record_sample(sink: &SampleSink, sensor_id: &SensorId, message: &PhysioSample) {
    if !message.valid {
        return;
    }
    let sample = SensorSample {
        sensor_id: sensor_id.clone(),
        value: sensor_value(message.data),
        timestamp_ms: sample_timestamp_ms(message),
    };
    sink.lock()
        .unwrap_or_else(PoisonError::into_inner)
        .insert(sensor_id.clone(), sample);
}

/// 把 `f32` 采样转成 JSON 数字。
///
/// 直接提升为 `f64` 会放大二进制误差（`97.58` 变成 `97.5800018...`），
/// 因此先取 `f32` 的最短往返文本再解析为 `f64`；非有限值转为 `null`。
fn sensor_value(data: f32) -> Value {
    data.to_string()
        .parse::<f64>()
        .map_or(Value::Null, Value::from)
}

/// 用消息自带的 ROS 时间戳生成 Unix epoch milliseconds。
fn sample_timestamp_ms(message: &PhysioSample) -> u64 {
    let seconds = i64::from(message.timestamp.sec).max(0) as u64;
    let millis = u64::from(message.timestamp.nanosec / 1_000_000);
    seconds.saturating_mul(1_000).saturating_add(millis)
}
