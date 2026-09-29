use map::NodeId;

#[derive(Debug, Clone, PartialEq, Eq)]
/// 规划结果：按访问顺序排列的节点序列与总代价。
pub struct Path {
    /// 从起点到终点的节点序列，起点在前、终点在后。
    pub nodes: Vec<NodeId>,
    /// 序列中相邻节点之间的代价之和。
    pub cost: u64,
}
