use crate::error::MapError;
use crate::graph::MapData;
use std::path::Path;

const DEFAULT_MAP_JSON: &str = include_str!("../../../../config/maps/default.json");

/// 从 JSON 文件加载规定的地图格式数据。
///
/// 文件内容必须是 [`MapData`] 的 JSON 表示，读取后立即校验。
///
/// # 错误
///
/// 返回 [`MapError::Io`]（文件不可读）、[`MapError::Malformed`]（JSON 或字段
/// 形状不合法）或 [`MapData::validate`] 定义的结构错误。
pub fn load_map(path: impl AsRef<Path>) -> Result<MapData, MapError> {
    let path = path.as_ref();
    let content = read_map_file(path)?;
    parse_map(&content)
}

/// 返回内置的默认地图数据。
///
/// 内容来自 `ros2_ws/config/maps/default.json`，与 [`load_map`] 使用同一套格式。
///
/// # Panic
///
/// 内嵌地图违反 [`MapData::validate`] 时 panic；该数据随仓库构建，属配置错误。
pub fn default_map() -> MapData {
    parse_map(DEFAULT_MAP_JSON).expect("default map must satisfy MapData::validate")
}

fn read_map_file(path: &Path) -> Result<String, MapError> {
    let location = path.display().to_string();
    let content = std::fs::read_to_string(path);
    content.map_err(|error| MapError::Io(format!("{location}: {error}")))
}

fn parse_map(raw: &str) -> Result<MapData, MapError> {
    let parsed = serde_json::from_str(raw);
    let map = parsed.map_err(|error| MapError::Malformed(error.to_string()))?;
    map.validate()?;
    Ok(map)
}
