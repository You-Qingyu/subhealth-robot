use crate::graph::NodeId;

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
/// 地图加载与地图格式校验的业务错误。
pub enum MapError {
    /// 地图文件无法读取。
    #[error("map file is not readable: {0}")]
    Io(String),
    /// 地图内容不是合法 YAML，或字段不符合规定的地图格式。
    #[error("map data is malformed: {0}")]
    Malformed(String),
    /// MAP_CONFIG 未设置。
    #[error("MAP_CONFIG is not set")]
    MissingConfig,
    /// MAP_CONFIG 指向的路径无效。
    #[error("MAP_CONFIG is invalid: {0}")]
    InvalidConfig(String),
    /// 地图格式版本不受支持。
    #[error("unsupported map version {0}")]
    UnsupportedVersion(u32),
    /// 地图中存在重复的节点标识。
    #[error("node {0:?} is defined more than once")]
    DuplicateNode(NodeId),
    /// 边引用了地图上不存在的节点。
    #[error("edge references unknown node {0:?}")]
    UnknownNode(NodeId),
    /// 地图中存在重复的节点名称。
    #[error("node name {0:?} is defined more than once")]
    DuplicateNodeName(String),
    /// 名称不对应任何节点。
    #[error("node named {0:?} does not exist on the map")]
    UnknownNodeName(String),
    /// 边的通行代价必须为正数。
    #[error("edge {from:?}-{to:?} must have a positive weight")]
    NonPositiveWeight { from: NodeId, to: NodeId },
}
