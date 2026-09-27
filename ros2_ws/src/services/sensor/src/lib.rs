//! 多个 [`platform::SensorProvider`] 的内存注册表。
//!
//! Registry 只负责聚合描述、查询和订阅，不负责传感器数据解释或任务决策。

use platform::SensorId;
use platform::{SensorDescriptor, SensorFilter, SensorProvider, SensorSample, SensorStream};
use std::sync::Arc;

#[derive(Default)]
/// 聚合多个传感器 provider 的注册表。
pub struct SensorRegistry {
    providers: Vec<Arc<dyn SensorProvider>>,
}

impl SensorRegistry {
    /// 注册一个 provider。
    ///
    /// Provider 会按注册顺序参与描述聚合和查询。
    pub fn register(&mut self, provider: Arc<dyn SensorProvider>) {
        self.providers.push(provider);
    }

    /// 返回所有已注册 provider 的传感器描述。
    pub fn descriptors(&self) -> Vec<SensorDescriptor> {
        self.providers
            .iter()
            .flat_map(|provider| provider.descriptors())
            .collect()
    }

    /// 返回第一个能提供指定传感器最新值的 provider 的结果。
    pub fn latest(&self, id: &SensorId) -> Option<SensorSample> {
        self.providers
            .iter()
            .find_map(|provider| provider.latest(id))
    }

    /// 为包含筛选 ID 的第一个 provider 建立订阅。
    ///
    /// 没有匹配 provider 时返回 `None`。
    pub fn subscribe(&self, filter: SensorFilter) -> Option<SensorStream> {
        self.providers
            .iter()
            .find(|provider| {
                provider
                    .descriptors()
                    .iter()
                    .any(|descriptor| filter.ids.contains(&descriptor.id))
            })
            .map(|provider| provider.subscribe(filter))
    }
}
