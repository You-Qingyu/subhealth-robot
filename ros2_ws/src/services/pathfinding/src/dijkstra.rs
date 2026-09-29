use crate::error::PathfindingError;
use crate::path::Path;
use map::{MapData, NodeId};
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

/// 邻接表：节点到邻居及其通行代价，累计代价使用 `u64` 避免溢出。
type Adjacency = HashMap<NodeId, Vec<(NodeId, u64)>>;

/// 一次成功搜索的结果：到终点的总代价与回溯表。
struct Reached {
    cost: u64,
    previous: HashMap<NodeId, NodeId>,
}

/// 规划从 `start` 到 `goal` 的最小代价路径。
///
/// 地图格式是无向图，[`MapData::edges`] 中的每条边都允许双向通行且代价相同。
/// `start` 与 `goal` 相同时返回只含该节点、代价为 `0` 的路径。
///
/// # 错误
///
/// - [`PathfindingError::UnknownNode`]：`start` 或 `goal` 不在地图上。
/// - [`PathfindingError::Unreachable`]：两者之间不存在完整路径。
pub fn shortest_path(map: &MapData, start: NodeId, goal: NodeId) -> Result<Path, PathfindingError> {
    ensure_node(map, start)?;
    ensure_node(map, goal)?;

    let index = adjacency(map);
    let reached = search(&index, start, goal)?;
    let nodes = reconstruct(&reached.previous, start, goal)?;

    Ok(Path {
        nodes,
        cost: reached.cost,
    })
}

fn ensure_node(map: &MapData, id: NodeId) -> Result<(), PathfindingError> {
    if map.nodes.iter().any(|node| node.id == id) {
        Ok(())
    } else {
        Err(PathfindingError::UnknownNode(id))
    }
}

fn adjacency(map: &MapData) -> Adjacency {
    let mut index: Adjacency = HashMap::new();
    for edge in &map.edges {
        let weight = u64::from(edge.weight);
        index.entry(edge.from).or_default().push((edge.to, weight));
        index.entry(edge.to).or_default().push((edge.from, weight));
    }
    index
}

/// Dijkstra 主循环：按代价从小到大扩展，首次弹出终点即得到最优解。
fn search(index: &Adjacency, start: NodeId, goal: NodeId) -> Result<Reached, PathfindingError> {
    let mut cost_so_far: HashMap<NodeId, u64> = HashMap::new();
    let mut previous: HashMap<NodeId, NodeId> = HashMap::new();
    let mut queue: BinaryHeap<Reverse<(u64, NodeId)>> = BinaryHeap::new();

    cost_so_far.insert(start, 0);
    queue.push(Reverse((0, start)));

    while let Some(Reverse((cost, node))) = queue.pop() {
        if node == goal {
            return Ok(Reached { cost, previous });
        }
        if cost > known_cost(&cost_so_far, node) {
            continue;
        }
        for &(next, weight) in index.get(&node).into_iter().flatten() {
            let next_cost = cost + weight;
            if next_cost >= known_cost(&cost_so_far, next) {
                continue;
            }
            cost_so_far.insert(next, next_cost);
            previous.insert(next, node);
            queue.push(Reverse((next_cost, next)));
        }
    }

    Err(unreachable_error(start, goal))
}

/// 返回节点当前已知的最小代价；尚未访问的节点视为无穷大。
fn known_cost(cost_so_far: &HashMap<NodeId, u64>, node: NodeId) -> u64 {
    cost_so_far.get(&node).copied().unwrap_or(u64::MAX)
}

/// 构造“起点与终点之间没有路径”的规划错误。
fn unreachable_error(from: NodeId, to: NodeId) -> PathfindingError {
    PathfindingError::Unreachable { from, to }
}

/// 沿回溯表从终点走到起点，得到按访问顺序排列的节点序列。
fn reconstruct(
    previous: &HashMap<NodeId, NodeId>,
    start: NodeId,
    goal: NodeId,
) -> Result<Vec<NodeId>, PathfindingError> {
    let mut nodes = vec![goal];
    let mut current = goal;
    while current != start {
        let upstream = previous.get(&current);
        current = *upstream.ok_or_else(|| unreachable_error(start, goal))?;
        nodes.push(current);
    }
    nodes.reverse();
    Ok(nodes)
}
