use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

use futures_util::StreamExt;
use orchestration::{OrchestrationError, Orchestrator};
use platform::{
    ExecutionFeedback, ExecutionResult, ExecutionSession, SensorDescriptor, SensorId, SystemEvent,
    TaskId, TaskRecord, TaskRepository,
};
use sensor::SensorRegistry;
use tokio::sync::{broadcast, Mutex};

use crate::dto::{CreateTask, SensorReading};

#[derive(Clone)]
/// Gateway 共享的运行时状态。
///
/// Repository 是任务状态的唯一来源；事件 channel 只传播状态变化通知。
pub struct AppState {
    inner: Arc<AppStateInner>,
}

pub struct AppStateInner {
    repository: Arc<dyn TaskRepository>,
    event_sequence: AtomicU64,
    events: broadcast::Sender<(u64, SystemEvent)>,
    orchestrator: Mutex<Orchestrator>,
    sensors: Arc<SensorRegistry>,
}

impl AppState {
    /// 创建 Gateway 状态并绑定共享的编排器、Repository 和传感器注册表。
    pub fn new(
        orchestrator: Orchestrator,
        repository: Arc<dyn TaskRepository>,
        sensors: Arc<SensorRegistry>,
    ) -> Self {
        let (events, _) = broadcast::channel(128);
        Self {
            inner: Arc::new(AppStateInner {
                repository,
                event_sequence: AtomicU64::new(0),
                events,
                orchestrator: Mutex::new(orchestrator),
                sensors,
            }),
        }
    }

    /// 返回当前地图中的 Tag 标识和名称，不暴露路径边与权重。
    pub async fn tags(&self) -> Vec<map::MapNode> {
        self.inner.orchestrator.lock().await.tags().to_vec()
    }

    /// 返回已注册的全部传感器描述。
    pub fn sensors(&self) -> Vec<SensorDescriptor> {
        self.inner.sensors.descriptors()
    }

    /// 读取指定传感器的描述和最新采样；传感器未注册时返回 `None`。
    pub fn sensor(&self, id: &str) -> Option<SensorReading> {
        let sensor_id = SensorId(id.to_owned());
        let descriptor = self.inner.sensors.descriptor(&sensor_id)?;
        let sample = self.inner.sensors.latest(&sensor_id);
        Some(SensorReading { descriptor, sample })
    }

    /// 提交任务，并在接受后异步消费执行会话。
    pub async fn create_task(&self, input: CreateTask) -> Result<TaskRecord, OrchestrationError> {
        let (record, session) = self
            .inner
            .orchestrator
            .lock()
            .await
            .submit(input.into_task())
            .await?;
        self.emit_task_state(&record);
        self.consume_session(record.task.id.clone(), session);
        Ok(record)
    }

    /// 返回 Repository 中的全部任务记录。
    pub fn list_tasks(&self) -> Result<Vec<TaskRecord>, OrchestrationError> {
        self.inner
            .repository
            .list_tasks()
            .map_err(OrchestrationError::from)
    }

    /// 读取指定任务记录。
    pub fn task(&self, id: &TaskId) -> Result<TaskRecord, OrchestrationError> {
        self.inner
            .repository
            .get_task(id)
            .map_err(OrchestrationError::from)
    }

    /// 创建一个接收状态变化通知的订阅者。
    pub fn subscribe(&self) -> broadcast::Receiver<(u64, SystemEvent)> {
        self.inner.events.subscribe()
    }

    fn consume_session(&self, task_id: TaskId, session: ExecutionSession) {
        let state = self.clone();
        tokio::spawn(async move {
            state.apply_session(task_id, session).await;
        });
    }

    async fn apply_session(&self, task_id: TaskId, session: ExecutionSession) {
        let ExecutionSession {
            mut feedback,
            result,
        } = session;

        while let Some(feedback) = feedback.next().await {
            match feedback {
                Ok(feedback) => self.apply_feedback(feedback).await,
                Err(error) => {
                    self.apply_execution_error(&task_id, error).await;
                    return;
                }
            }
        }

        match result.await {
            Ok(result) => self.apply_result(result).await,
            Err(error) => self.apply_execution_error(&task_id, error).await,
        }
    }

    async fn apply_execution_error(&self, task_id: &TaskId, error: platform::ExecutionError) {
        tracing::warn!(%error, task_id = %task_id.0, "execution session failed");
        self.apply_result(ExecutionResult {
            task_id: task_id.clone(),
            state: "failed".into(),
        })
        .await;
    }

    async fn apply_feedback(&self, feedback: ExecutionFeedback) {
        let record = match self.inner.orchestrator.lock().await.feedback(feedback) {
            Ok(record) => record,
            Err(error) => {
                tracing::warn!(%error, "unable to apply execution feedback");
                return;
            }
        };
        self.emit_task_state(&record);
    }

    async fn apply_result(&self, result: ExecutionResult) {
        let record = match self.inner.orchestrator.lock().await.complete(result) {
            Ok(record) => record,
            Err(error) => {
                tracing::warn!(%error, "unable to apply execution result");
                return;
            }
        };
        self.emit_task_state(&record);
    }

    fn emit_task_state(&self, record: &TaskRecord) {
        let sequence = self.inner.event_sequence.fetch_add(1, Ordering::Relaxed) + 1;
        let _ = self.inner.events.send((
            sequence,
            SystemEvent::TaskStateChanged {
                task_id: record.task.id.clone(),
                state: record.state.clone(),
            },
        ));
    }
}
