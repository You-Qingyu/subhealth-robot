//! 规定的地图格式与地图数据入口。
//!
//! 本 crate 负责地图格式类型、格式校验和地图数据加载，不包含任何寻路逻辑。
//! 寻路统一由 orchestration 基于 [`MapData`] 完成。
//!
//! 地图格式是节点-边加权无向图：
//!
//! - [`MapNode`] 描述一个可到达位置；
//! - [`MapEdge`] 描述两个节点之间可双向通行的关系，代价必须为正；
//! - [`MapData`] 是唯一的地图数据结构，也是 [`load_map`] 的返回类型。

mod error;
mod graph;
mod loader;

pub use error::MapError;
pub use graph::{MapData, MapEdge, MapNode, NodeId};
pub use loader::load_map;
