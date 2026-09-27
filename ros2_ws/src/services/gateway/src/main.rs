use std::sync::Arc;

use execution::Execution;
use gateway::{app, AppState};
use orchestration::Orchestrator;
use platform::TaskRepository;
use task_repository::InMemoryTaskRepository;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let port = std::env::var("GATEWAY_HTTP_PORT").unwrap_or_else(|_| "5000".into());
    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}")).await?;

    tracing_subscriber::fmt::init();

    let repository: Arc<dyn TaskRepository> = Arc::new(InMemoryTaskRepository::new());
    let execution = Arc::new(Execution::init()?);
    let state = AppState::new(
        Orchestrator::new(execution.clone(), repository.clone()),
        repository.clone(),
    );
    axum::serve(listener, app(state)).await?;
    execution.shutdown()?;
    Ok(())
}
