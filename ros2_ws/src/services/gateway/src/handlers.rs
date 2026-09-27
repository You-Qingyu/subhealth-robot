use orchestration::OrchestrationError;
use platform::TaskId;

use crate::{dto::CreateTask, state::AppState};
use axum::{
    extract::{Path, State, WebSocketUpgrade},
    http::StatusCode,
    response::IntoResponse,
    Json,
};

pub async fn list_tasks(
    State(state): State<AppState>,
) -> Result<Json<Vec<platform::TaskRecord>>, StatusCode> {
    state.list_tasks().map(Json).map_err(repository_status)
}

pub async fn create_task(
    State(state): State<AppState>,
    Json(input): Json<CreateTask>,
) -> Result<(StatusCode, Json<platform::TaskRecord>), StatusCode> {
    tracing::info!(
        device_id = ?input.device_id,
        primitive = ?input.primitive,
        target = ?input.target,
        deadline_ms = ?input.deadline_ms,
        "gateway received task request"
    );
    state
        .create_task(input)
        .await
        .map(|view| (StatusCode::ACCEPTED, Json(view)))
        .map_err(submission_status)
}

pub async fn get_task(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<platform::TaskRecord>, StatusCode> {
    state.task(&TaskId(id)).map(Json).map_err(repository_status)
}

pub async fn events(State(state): State<AppState>, ws: WebSocketUpgrade) -> impl IntoResponse {
    let mut receiver = state.subscribe();
    ws.on_upgrade(move |mut socket| async move {
        while let Ok((sequence, event)) = receiver.recv().await {
            let payload = serde_json::json!({ "sequence": sequence, "event": event });
            if socket
                .send(axum::extract::ws::Message::Text(payload.to_string().into()))
                .await
                .is_err()
            {
                break;
            }
        }
    })
}

fn submission_status(error: OrchestrationError) -> StatusCode {
    match error {
        OrchestrationError::Busy
        | OrchestrationError::Duplicate
        | OrchestrationError::TerminalTask => StatusCode::CONFLICT,
        OrchestrationError::InvalidTarget => StatusCode::BAD_REQUEST,
        OrchestrationError::Repository(_) => StatusCode::INTERNAL_SERVER_ERROR,
        OrchestrationError::Execution(_) => StatusCode::BAD_GATEWAY,
        OrchestrationError::UnknownTask => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

fn repository_status(error: OrchestrationError) -> StatusCode {
    match error {
        OrchestrationError::UnknownTask => StatusCode::NOT_FOUND,
        _ => StatusCode::INTERNAL_SERVER_ERROR,
    }
}
