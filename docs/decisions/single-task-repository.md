# 单一任务状态源

## 决策

已接受任务及其状态、进度和阶段只由 `TaskRepository` 持有。Gateway 和 Orchestration 共享同一个 Repository 实例。

## 动机

如果 Gateway、Orchestration 或 transport 各自保存任务副本，状态转换会出现竞争和分歧。集中状态可以让反馈和终态结果以原子操作应用，并保留 terminal record。

## 结果

- Execution 只执行，不持有任务存储。
- Gateway 只能查询或通过 Orchestrator 提交任务。
- Repository 的错误和状态转换是模块接口的一部分。
