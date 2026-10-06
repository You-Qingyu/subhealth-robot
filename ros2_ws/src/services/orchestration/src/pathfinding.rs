use map::{MapData, NodeId};
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Path {
    pub nodes: Vec<NodeId>,
    pub cost: u64,
}

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
pub enum PathfindingError {
    #[error("node {0:?} does not exist on the map")]
    UnknownNode(NodeId),
    #[error("no path from {from:?} to {to:?}")]
    Unreachable { from: NodeId, to: NodeId },
}

pub fn shortest_path(map: &MapData, start: NodeId, goal: NodeId) -> Result<Path, PathfindingError> {
    ensure_node(map, start)?;
    ensure_node(map, goal)?;
    let mut costs = HashMap::from([(start, 0_u64)]);
    let mut previous = HashMap::new();
    let mut queue = BinaryHeap::from([Reverse((0_u64, start))]);
    while let Some(Reverse((cost, node))) = queue.pop() {
        if node == goal {
            return Ok(Path {
                nodes: reconstruct(&previous, start, goal)?,
                cost,
            });
        }
        if cost > costs.get(&node).copied().unwrap_or(u64::MAX) {
            continue;
        }
        for edge in map
            .edges
            .iter()
            .filter(|edge| edge.from == node || edge.to == node)
        {
            let next = if edge.from == node {
                edge.to
            } else {
                edge.from
            };
            let next_cost = cost + u64::from(edge.weight);
            if next_cost < costs.get(&next).copied().unwrap_or(u64::MAX) {
                costs.insert(next, next_cost);
                previous.insert(next, node);
                queue.push(Reverse((next_cost, next)));
            }
        }
    }
    Err(PathfindingError::Unreachable {
        from: start,
        to: goal,
    })
}

fn ensure_node(map: &MapData, id: NodeId) -> Result<(), PathfindingError> {
    map.nodes
        .iter()
        .any(|node| node.id == id)
        .then_some(())
        .ok_or(PathfindingError::UnknownNode(id))
}

fn reconstruct(
    previous: &HashMap<NodeId, NodeId>,
    start: NodeId,
    goal: NodeId,
) -> Result<Vec<NodeId>, PathfindingError> {
    let mut nodes = vec![goal];
    let mut current = goal;
    while current != start {
        current = *previous
            .get(&current)
            .ok_or(PathfindingError::Unreachable {
                from: start,
                to: goal,
            })?;
        nodes.push(current);
    }
    nodes.reverse();
    Ok(nodes)
}
