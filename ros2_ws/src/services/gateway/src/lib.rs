//! HTTP 和 WebSocket 到控制平面的入口。
//!
//! Gateway 将外部请求映射为 canonical task，并通过 [`AppState`] 调用
//! Orchestration；它不拥有任务状态。

use axum::{routing::get, Router};

mod dto;
mod handlers;
mod state;

pub use dto::CreateTask;
pub use state::AppState;

use crate::handlers::{create_task, events, get_task, list_tasks};

/// 根据当前应用状态构造 Gateway router。
pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/api/v1/tasks", get(list_tasks).post(create_task))
        .route("/api/v1/tasks/{id}", get(get_task))
        .route("/api/v1/events", get(events))
        .with_state(state)
}
