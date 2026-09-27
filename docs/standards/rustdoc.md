# Rustdoc 编写准则

Rustdoc 描述当前代码提供的局部接口。它不替代 `docs/interfaces/` 中的模块关系说明，也不替代 `docs/decisions/` 中的架构取舍。

## 语言和格式

- Rustdoc 正文使用中文；代码标识符保持英文。
- `//!` 用于 crate 或模块说明，`///` 用于公开项说明，`//` 用于局部实现说明。
- 类型、函数、字段、配置项和枚举值使用 backtick。
- 类型和函数优先使用 intra-doc link，例如 [`TaskRepository`] 或 [`TaskRepository::create_task`]。
- 自然语言尽量控制在 80 列以内；Rust 代码由 `cargo fmt` 格式化。
- 只有确实适用时才添加 `# 错误`、`# 示例`、`# 生命周期`、`# Panic` 和 `# Safety` 章节。

## 内容要求

跨模块公开的 `pub` 类型、trait、函数、方法、字段和错误变体应说明：

- 作用和动机；
- 参数与返回值的业务语义；
- 错误及其发生条件；
- 状态转换、调用顺序、生命周期和副作用；
- 调用者不能仅从类型签名推导出的不变量。

不要求为每个私有函数添加 Rustdoc，也不要把尚未实现的未来行为写成当前契约。

## 分层

- Rustdoc：类型、函数和局部接口语义。
- `docs/interfaces/`：模块之间的 seam、调用关系和公开入口。
- `docs/decisions/`：跨模块设计动机和取舍。

## 检查

修改 Rustdoc 后运行：

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo doc --workspace --no-deps
```

暂不全局启用 `missing_docs`；先补齐核心公开 seam，再单独评估各 crate 的启用范围。
