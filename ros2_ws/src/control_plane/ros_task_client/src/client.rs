use std::{
    collections::HashMap,
    fmt,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};

use platform::{ExecutionError, ExecutionFeedback, ExecutionResult, ExecutionSession, Task};
use rclrs::{ActionClient, CreateBasicExecutor, GoalClient, Node, TopicNamesAndTypes};
use ros_env::task_interfaces::action::{ExecuteTask, ExecuteTask_Feedback};
use tokio::{
    sync::{mpsc, oneshot, watch},
    time::Instant,
};
use tokio_stream::wrappers::ReceiverStream;
use tracing::info;

use crate::{
    mapper::{from_ros_feedback, from_ros_result, to_ros_goal},
    DeviceConfig, RosTaskClientConfig, RosTaskError, RosTaskRuntime,
};

struct DeviceHandler {
    action_name: String,
    action_client: ActionClient<ExecuteTask>,
}

struct DeviceRegistry {
    handlers: HashMap<String, DeviceHandler>,
}

impl DeviceRegistry {
    fn new(node: &Node, devices: Vec<DeviceConfig>) -> Result<Self, RosTaskError> {
        let mut handlers = HashMap::with_capacity(devices.len());
        for device in devices.into_iter().filter(|device| device.enabled) {
            let action_client = node
                .create_action_client::<ExecuteTask>(&device.action_name)
                .map_err(ros_error)?;
            handlers.insert(
                device.id,
                DeviceHandler {
                    action_name: device.action_name,
                    action_client,
                },
            );
        }
        Ok(Self { handlers })
    }

    fn resolve(&self, device_id: &str) -> Result<&DeviceHandler, RosTaskError> {
        self.handlers
            .get(device_id)
            .ok_or_else(|| RosTaskError::UnknownDevice {
                device_id: device_id.into(),
            })
    }

    fn len(&self) -> usize {
        self.handlers.len()
    }
}

const ACTION_POLL_INTERVAL: Duration = Duration::from_millis(25);
const READY_FEEDBACK_DRAIN_LIMIT: usize = 16;

struct ClientState {
    node: Node,
    registry: DeviceRegistry,
    stopping: Arc<AtomicBool>,
    shutdown_rx: watch::Receiver<bool>,
    feedback_buffer: usize,
    server_wait_timeout: Duration,
}

#[derive(Clone)]
/// 将 canonical task 路由到已注册 ROS action server 的客户端。
pub struct RosTaskClient {
    state: Arc<ClientState>,
}

impl RosTaskClient {
    /// 从 `ROS_TASK_CLIENT_CONFIG` 初始化 client 和 ROS runtime。
    pub fn init() -> Result<(Self, RosTaskRuntime), RosTaskError> {
        let config = RosTaskClientConfig::from_environment()?;
        Self::init_with_config(config)
    }

    /// 使用显式配置初始化 client 和 ROS runtime。
    pub fn init_with_config(
        config: RosTaskClientConfig,
    ) -> Result<(Self, RosTaskRuntime), RosTaskError> {
        config.validate()?;
        let context = rclrs::Context::default_from_env().map_err(ros_error)?;
        let executor = context.create_basic_executor();
        let node = executor
            .create_node(config.ros.node_name.as_str())
            .map_err(ros_error)?;
        let registry = DeviceRegistry::new(&node, config.devices)?;
        let stopping = Arc::new(AtomicBool::new(false));
        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let runtime = RosTaskRuntime::start(executor, Arc::clone(&stopping), shutdown_tx)?;
        Ok((
            Self {
                state: Arc::new(ClientState {
                    node,
                    registry,
                    stopping,
                    shutdown_rx,
                    feedback_buffer: config.ros.feedback_buffer,
                    server_wait_timeout: Duration::from_millis(config.ros.server_wait_timeout_ms),
                }),
            },
            runtime,
        ))
    }

    /// 检查任务的设备是否存在于 enabled registry 中。
    pub async fn validate(&self, task: &Task) -> Result<(), RosTaskError> {
        self.state.registry.resolve(&task.device_id.0)?;
        Ok(())
    }

    /// 向目标 ROS action server 发送任务并返回执行会话。
    ///
    /// action server 的反馈会进入 [`platform::ExecutionSession::feedback`]，
    /// 最终结果会进入 [`platform::ExecutionSession::result`]。
    pub async fn execute(&self, task: Task) -> Result<ExecutionSession, ExecutionError> {
        info!(
            task_id = %task.id.0,
            device_id = %task.device_id.0,
            primitive = ?task.primitive,
            target = ?task.target,
            deadline_ms = ?task.deadline_ms,
            "ROS client executing task request"
        );
        let handler = self.state.registry.resolve(&task.device_id.0)?;
        let goal = self.request_goal(&task, handler).await?;
        let (feedback_tx, feedback_rx) = mpsc::channel(self.state.feedback_buffer);
        let (result_tx, result_rx) = oneshot::channel();
        let shutdown_rx = self.state.shutdown_rx.clone();
        tokio::spawn(async move {
            let result = relay_goal(goal, &task.id.0, feedback_tx, shutdown_rx).await;
            let _ = result_tx.send(result);
        });
        Ok(ExecutionSession {
            feedback: Box::pin(ReceiverStream::new(feedback_rx)),
            result: Box::pin(async move {
                result_rx
                    .await
                    .map_err(|_| RosTaskError::ChannelClosed { channel: "result" })?
                    .map_err(ExecutionError::from)
            }),
        })
    }

    async fn request_goal(
        &self,
        command: &Task,
        handler: &DeviceHandler,
    ) -> Result<GoalClient<ExecuteTask>, RosTaskError> {
        let state = &self.state;
        if state.stopping.load(Ordering::Acquire) || *state.shutdown_rx.borrow() {
            return Err(RosTaskError::Shutdown);
        }
        let raw_goal = to_ros_goal(command)?;
        let deadline = Instant::now() + state.server_wait_timeout;
        let mut shutdown_rx = state.shutdown_rx.clone();
        wait_for_server(
            &state.node,
            handler,
            &command.device_id.0,
            deadline,
            &mut shutdown_rx,
        )
        .await?;
        if Instant::now() >= deadline {
            return Err(unavailable(handler, &command.device_id.0));
        }
        let requested_goal = handler
            .action_client
            .try_request_goal(raw_goal)
            .map_err(ros_error)?;
        let accepted = tokio::select! {
            biased;
            _ = shutdown_rx.changed() => return Err(RosTaskError::Shutdown),
            accepted = tokio::time::timeout_at(deadline, requested_goal) => {
                accepted.map_err(|_| unavailable(handler, &command.device_id.0))?
            }
        };
        accepted.ok_or_else(|| RosTaskError::GoalRejected {
            task_id: command.id.0.clone(),
        })
    }
}

async fn wait_for_server(
    node: &Node,
    handler: &DeviceHandler,
    device_id: &str,
    deadline: Instant,
    shutdown_rx: &mut watch::Receiver<bool>,
) -> Result<(), RosTaskError> {
    loop {
        if *shutdown_rx.borrow() {
            return Err(RosTaskError::Shutdown);
        }
        let now = Instant::now();
        if now >= deadline {
            return Err(unavailable(handler, device_id));
        }
        if action_server_is_ready(node, &handler.action_name).map_err(ros_error)? {
            return Ok(());
        }
        tokio::select! {
            biased;
            _ = shutdown_rx.changed() => return Err(RosTaskError::Shutdown),
            () = tokio::time::sleep(ACTION_POLL_INTERVAL.min(deadline - now)) => {}
        }
    }
}

async fn relay_goal(
    goal: GoalClient<ExecuteTask>,
    task_id: &str,
    feedback_tx: mpsc::Sender<Result<ExecutionFeedback, ExecutionError>>,
    mut shutdown_rx: watch::Receiver<bool>,
) -> Result<ExecutionResult, RosTaskError> {
    let GoalClient {
        mut feedback,
        result,
        ..
    } = goal;
    tokio::pin!(result);
    let mut feedback_open = true;
    if *shutdown_rx.borrow() {
        return Err(RosTaskError::Shutdown);
    }
    loop {
        tokio::select! {
            biased;
            _ = shutdown_rx.changed() => return Err(RosTaskError::Shutdown),
            terminal = result.as_mut() => {
                drain_ready_feedback(&mut feedback, &feedback_tx, task_id)?;
                return from_ros_result(task_id, terminal.0, terminal.1);
            }
            raw = feedback.recv(), if feedback_open => {
                match raw {
                    Some(raw) => map_and_try_send_feedback(&feedback_tx, task_id, raw)?,
                    None => feedback_open = false,
                }
            }
        }
    }
}

fn drain_ready_feedback(
    feedback: &mut mpsc::UnboundedReceiver<ExecuteTask_Feedback>,
    feedback_tx: &mpsc::Sender<Result<ExecutionFeedback, ExecutionError>>,
    task_id: &str,
) -> Result<(), RosTaskError> {
    for _ in 0..READY_FEEDBACK_DRAIN_LIMIT {
        let Ok(raw) = feedback.try_recv() else { break };
        map_and_try_send_feedback(feedback_tx, task_id, raw)?;
    }
    Ok(())
}

fn map_and_try_send_feedback(
    feedback_tx: &mpsc::Sender<Result<ExecutionFeedback, ExecutionError>>,
    task_id: &str,
    raw: ExecuteTask_Feedback,
) -> Result<(), RosTaskError> {
    let mapped = from_ros_feedback(task_id, raw)?;
    match feedback_tx.try_send(Ok(mapped)) {
        Ok(()) => Ok(()),
        Err(mpsc::error::TrySendError::Full(_)) => Err(RosTaskError::FeedbackOverflow {
            task_id: task_id.into(),
            capacity: feedback_tx.max_capacity(),
        }),
        Err(mpsc::error::TrySendError::Closed(_)) => Err(RosTaskError::ChannelClosed {
            channel: "feedback",
        }),
    }
}

fn unavailable(handler: &DeviceHandler, device_id: &str) -> RosTaskError {
    RosTaskError::ActionServerUnavailable {
        device_id: device_id.into(),
        action_name: handler.action_name.clone(),
    }
}

fn action_server_is_ready(node: &Node, action_name: &str) -> Result<bool, rclrs::RclrsError> {
    let mut services = TopicNamesAndTypes::new();
    let mut publishers = TopicNamesAndTypes::new();
    for server_node in node.get_node_names()? {
        if let Ok(names) =
            node.get_service_names_and_types_by_node(&server_node.name, &server_node.namespace)
        {
            merge_names_and_types(&mut services, names);
        }
        if let Ok(names) =
            node.get_publisher_names_and_types_by_node(&server_node.name, &server_node.namespace)
        {
            merge_names_and_types(&mut publishers, names);
        }
    }
    Ok(action_entities_are_ready(
        action_name,
        &services,
        &publishers,
    ))
}

fn merge_names_and_types(target: &mut TopicNamesAndTypes, source: TopicNamesAndTypes) {
    for (name, types) in source {
        target.entry(name).or_default().extend(types);
    }
}

fn action_entities_are_ready(
    action_name: &str,
    services: &TopicNamesAndTypes,
    publishers: &TopicNamesAndTypes,
) -> bool {
    [
        (
            services,
            "send_goal",
            "task_interfaces/action/ExecuteTask_SendGoal",
        ),
        (
            services,
            "get_result",
            "task_interfaces/action/ExecuteTask_GetResult",
        ),
        (
            publishers,
            "feedback",
            "task_interfaces/action/ExecuteTask_FeedbackMessage",
        ),
        (publishers, "status", "action_msgs/msg/GoalStatusArray"),
    ]
    .into_iter()
    .all(|(entities, suffix, expected)| {
        entities
            .get(&format!("{action_name}/_action/{suffix}"))
            .is_some_and(|types| types.iter().any(|actual| actual == expected))
    })
}

impl fmt::Debug for RosTaskClient {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("RosTaskClient")
            .field("device_count", &self.state.registry.len())
            .field("stopping", &self.state.stopping.load(Ordering::Acquire))
            .field("shutdown_requested", &*self.state.shutdown_rx.borrow())
            .field("feedback_buffer", &self.state.feedback_buffer)
            .field("server_wait_timeout", &self.state.server_wait_timeout)
            .finish_non_exhaustive()
    }
}

fn ros_error(error: rclrs::RclrsError) -> RosTaskError {
    RosTaskError::Ros(error.to_string())
}

#[cfg(test)]
mod tests {
    use super::RosTaskClient;

    #[test]
    fn client_is_cloneable_for_independent_submissions() {
        fn assert_clone<T: Clone>() {}

        assert_clone::<RosTaskClient>();
    }
}
