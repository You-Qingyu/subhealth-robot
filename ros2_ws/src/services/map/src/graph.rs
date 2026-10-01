use crate::error::MapError;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
/// 地图节点的稳定标识。
pub struct NodeId(pub u32);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// 地图上的一个可到达位置。
pub struct MapNode {
    /// 节点标识。
    pub id: NodeId,
    /// 面向调用者的节点名称。
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// 连接两个节点的通行关系。
///
/// 边是无向的：双向通行代价相同。
pub struct MapEdge {
    /// 一端的节点标识。
    pub from: NodeId,
    /// 另一端的节点标识。
    pub to: NodeId,
    /// 单次通行代价，必须为正数。
    pub weight: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// 规定的地图格式：节点-边加权无向图。
pub struct MapData {
    /// 地图格式版本。
    pub version: u32,
    /// 地图名称。
    pub name: String,
    /// 地图上的全部节点。
    pub nodes: Vec<MapNode>,
    /// 地图上的全部边。
    pub edges: Vec<MapEdge>,
}

impl MapData {
    /// 校验地图是否满足规定格式的不变量。
    ///
    /// 加载路径一定会调用此方法；自行构造 [`MapData`] 的调用者也应调用。
    ///
    /// # 错误
    ///
    /// 返回 [`MapError::DuplicateNode`]、[`MapError::UnknownNode`] 或
    /// [`MapError::NonPositiveWeight`]，分别对应节点重复、悬空边和非正代价。
    pub fn validate(&self) -> Result<(), MapError> {
        if self.version != 1 {
            return Err(MapError::UnsupportedVersion(self.version));
        }
        let ids = collect_node_ids(&self.nodes)?;
        collect_node_names(&self.nodes)?;
        validate_edges(&self.edges, &ids)?;
        Ok(())
    }

    /// 按名称解析节点。
    pub fn node_by_name(&self, name: &str) -> Result<NodeId, MapError> {
        self.nodes
            .iter()
            .find(|node| node.name == name)
            .map(|node| node.id)
            .ok_or_else(|| MapError::UnknownNodeName(name.to_owned()))
    }
}

fn collect_node_ids(nodes: &[MapNode]) -> Result<HashSet<NodeId>, MapError> {
    let mut ids = HashSet::with_capacity(nodes.len());
    for node in nodes {
        if !ids.insert(node.id) {
            return Err(MapError::DuplicateNode(node.id));
        }
    }
    Ok(ids)
}

fn collect_node_names(nodes: &[MapNode]) -> Result<HashMap<&str, NodeId>, MapError> {
    let mut names = HashMap::with_capacity(nodes.len());
    for node in nodes {
        if names.insert(node.name.as_str(), node.id).is_some() {
            return Err(MapError::DuplicateNodeName(node.name.clone()));
        }
    }
    Ok(names)
}

fn validate_edges(edges: &[MapEdge], ids: &HashSet<NodeId>) -> Result<(), MapError> {
    for edge in edges {
        ensure_known(ids, edge.from)?;
        ensure_known(ids, edge.to)?;
        if edge.weight == 0 {
            return Err(MapError::NonPositiveWeight {
                from: edge.from,
                to: edge.to,
            });
        }
    }
    Ok(())
}

fn ensure_known(ids: &HashSet<NodeId>, id: NodeId) -> Result<(), MapError> {
    if ids.contains(&id) {
        Ok(())
    } else {
        Err(MapError::UnknownNode(id))
    }
}
