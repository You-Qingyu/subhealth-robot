use map::NodeId;

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
/// 路径规划的业务错误。
pub enum PathfindingError {
    /// 起点或终点不在地图上。
    #[error("node {0:?} does not exist on the map")]
    UnknownNode(NodeId),
    /// 起点与终点之间不存在完整路径。
    #[error("no path from {from:?} to {to:?}")]
    Unreachable { from: NodeId, to: NodeId },
}
