use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

use platform::SensorId;
use rclrs::{CreateBasicExecutor, Node, QoSProfile, Subscription, SubscriptionOptions};
use ros_env::physio_interfaces::msg::PhysioSample;

use crate::provider::{descriptors_from, record_sample, RosSensorProvider, SampleSink};
use crate::{RosSensorConfig, RosSensorRuntime, SensorClientError, SensorConfig};

/// 加载配置、订阅全部传感器话题并启动 ROS executor。
pub(crate) fn connect() -> Result<(Arc<RosSensorProvider>, RosSensorRuntime), SensorClientError> {
    let config = RosSensorConfig::from_environment()?;
    let context = rclrs::Context::default_from_env().map_err(ros_error)?;
    let executor = context.create_basic_executor();
    let node = executor
        .create_node(config.ros.node_name.as_str())
        .map_err(ros_error)?;
    let samples: SampleSink = Arc::new(Mutex::new(HashMap::new()));
    let subscriptions = subscribe_all(&node, &config.sensors, &samples)?;
    let provider = Arc::new(RosSensorProvider::new(
        descriptors_from(&config.sensors),
        samples,
    ));
    let runtime = RosSensorRuntime::start(executor, node, subscriptions)?;
    Ok((provider, runtime))
}

/// 为每个配置的传感器创建订阅。
fn subscribe_all(
    node: &Node,
    sensors: &[SensorConfig],
    sink: &SampleSink,
) -> Result<Vec<Subscription<PhysioSample>>, SensorClientError> {
    sensors
        .iter()
        .map(|sensor| subscribe_one(node, sensor, sink))
        .collect()
}

/// 订阅单个传感器话题；QoS 对齐 mock publisher 的 RELIABLE/KEEP_LAST/depth-10。
fn subscribe_one(
    node: &Node,
    sensor: &SensorConfig,
    sink: &SampleSink,
) -> Result<Subscription<PhysioSample>, SensorClientError> {
    let sensor_id = SensorId(sensor.id.clone());
    let callback_sink = Arc::clone(sink);
    let mut options = SubscriptionOptions::new(sensor.topic.as_str());
    options.qos = QoSProfile::default().keep_last(10).reliable().volatile();
    node.create_subscription(options, move |message: PhysioSample| {
        record_sample(&callback_sink, &sensor_id, &message);
    })
    .map_err(ros_error)
}

fn ros_error(error: rclrs::RclrsError) -> SensorClientError {
    SensorClientError::Ros(error.to_string())
}
