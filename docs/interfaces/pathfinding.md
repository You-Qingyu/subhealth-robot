# Pathfinding 接口

## 动机

把寻路逻辑收敛到一个 crate：调用者只传入 `map` crate 规定的 `MapData`，不感知算法细节。

## 公开接口

- `shortest_path`：输入 `MapData`、起点和终点，返回 `Path`。
- `Path`：按访问顺序排列的节点序列与总代价。
- `PathfindingError`：起点/终点不存在，或两者不可达。

## 语义

- 唯一权威算法是 Dijkstra；边按无向边处理，与 `MapData::edges` 的方向约定一致。
- 返回的是最小总代价路径；总代价与路径节点序列一起给出，不返回中间态。
- 起点等于终点时返回只含该节点、代价为 `0` 的路径。
- 地图结构的有效性由 `MapData::validate` 负责，`shortest_path` 只检查起点和终点是否存在，不重复校验地图。

实现见 `ros2_ws/src/services/pathfinding/src`。
