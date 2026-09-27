# 事件是通知而非状态存储

## 决策

Gateway 在 Repository 状态转换后发布带递增序号的瞬时事件。事件不构成任务状态的第二份真相源。

## 动机

WebSocket 客户端需要实时更新，但实时通知不应复制完整任务生命周期。查询接口和 Repository 记录仍然是完整状态来源。

## 当前范围

当前 Gateway 发布 `TaskStateChanged`；`SystemEvent` 中的设备和传感器事件类型尚未由 Gateway 产生。WebSocket 当前不提供历史事件恢复协议。
