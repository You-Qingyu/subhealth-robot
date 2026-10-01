use crate::error::MapError;
use crate::graph::MapData;
use std::path::Path;

/// 从 `MAP_CONFIG` 指定的 YAML 文件加载规定的地图格式数据。
///
/// 文件内容必须是 [`MapData`] 的 YAML 表示，读取后立即校验。
///
/// # 错误
///
/// 返回 [`MapError::Io`]（文件不可读）、[`MapError::Malformed`]（YAML 或字段
/// 形状不合法）或 [`MapData::validate`] 定义的结构错误。
pub fn load_map() -> Result<MapData, MapError> {
    let path = std::env::var("MAP_CONFIG").map_err(|_| MapError::MissingConfig)?;
    if path.trim().is_empty() {
        return Err(MapError::InvalidConfig("path is empty".into()));
    }
    load_map_file(path)
}

fn load_map_file(path: impl AsRef<Path>) -> Result<MapData, MapError> {
    let path = path.as_ref();
    let content = read_map_file(path)?;
    parse_map(&content)
}

fn read_map_file(path: &Path) -> Result<String, MapError> {
    let location = path.display().to_string();
    let content = std::fs::read_to_string(path);
    content.map_err(|error| MapError::Io(format!("{location}: {error}")))
}

fn parse_map(raw: &str) -> Result<MapData, MapError> {
    let map: MapData =
        serde_yaml::from_str(raw).map_err(|error| MapError::Malformed(error.to_string()))?;
    map.validate()?;
    Ok(map)
}
