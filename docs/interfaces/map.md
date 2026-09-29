# Map 接口

## 动机

为寻路提供唯一、与算法无关的地图格式，并把地图数据的加载与校验从路径计算中分离出来。

## 公开接口

- `load_map`：从 JSON 文件读取地图，返回 `MapData`。
- `default_map`：返回内嵌的默认地图，返回类型同样是 `MapData`。
- `MapData::validate`：校验地图格式不变量。
- 格式类型：`MapData`、`MapNode`、`MapEdge`、`NodeId`、`MapError`。

## 语义

- 地图格式固定为节点-边加权无向图：`MapData` 是唯一的地图数据结构。
- 每条 `MapEdge` 可双向通行，双向代价相同，且代价必须为正。
- 加载失败以 `MapError` 返回，不返回部分数据；结构错误区分节点重复、悬空边和零代价。
- 地图 crate 不包含任何寻路逻辑。
- 默认地图数据在 `ros2_ws/config/maps/default.json`，它同时是 `default_map` 的内嵌来源和自定义地图的格式样例。

实现见 `ros2_ws/src/services/map/src`。
