//! 基于 [`map::MapData`] 的路径规划。
//!
//! 本 crate 是寻路逻辑的唯一入口：输入规定的地图格式数据，输出最小代价路径。
//! 当前唯一的权威算法是 Dijkstra，边按无向边处理。
//!
//! ```ignore
//! let map = map::default_map();
//! let path = pathfinding::shortest_path(&map, map::NodeId(1), map::NodeId(3))?;
//! ```

mod dijkstra;
mod error;
mod path;

pub use dijkstra::shortest_path;
pub use error::PathfindingError;
pub use path::Path;
