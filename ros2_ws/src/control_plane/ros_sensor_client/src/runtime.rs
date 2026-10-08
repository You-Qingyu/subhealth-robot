use std::{
    sync::{
        mpsc::{self, TryRecvError},
        Arc, Mutex, PoisonError,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use rclrs::{Executor, ExecutorCommands, Node, RclrsError, SpinOptions, Subscription};
use ros_env::physio_interfaces::msg::PhysioSample;

use crate::SensorClientError;

const STARTUP_TIMEOUT: Duration = Duration::from_secs(5);
const STARTUP_POLL_INTERVAL: Duration = Duration::from_millis(10);

/// 在独立线程中运行 ROS executor，并持有订阅句柄直到关闭。
pub struct RosSensorRuntime {
    commands: Arc<ExecutorCommands>,
    thread: Mutex<Option<JoinHandle<Vec<RclrsError>>>>,
    _node: Node,
    _subscriptions: Vec<Subscription<PhysioSample>>,
}

impl RosSensorRuntime {
    /// 启动 ROS executor 线程，等待其 readiness 后返回运行时。
    ///
    /// # 错误
    ///
    /// executor 线程无法启动，或在超时时间内没有开始运行时返回错误。
    pub(crate) fn start(
        executor: Executor,
        node: Node,
        subscriptions: Vec<Subscription<PhysioSample>>,
    ) -> Result<Self, SensorClientError> {
        let commands = Arc::clone(executor.commands());
        let (ready_tx, ready_rx) = mpsc::channel();
        drop(commands.run(async move {
            let _ = ready_tx.send(());
        }));
        let thread = spawn_spin(executor)?;
        if let Err(error) = await_ready(&ready_rx) {
            commands.halt_spinning();
            let _ = join_executor(thread);
            return Err(error);
        }
        Ok(Self {
            commands,
            thread: Mutex::new(Some(thread)),
            _node: node,
            _subscriptions: subscriptions,
        })
    }

    /// 请求 executor 停止并等待其线程完成；重复调用是安全的。
    pub fn shutdown(&self) -> Result<(), SensorClientError> {
        self.commands.halt_spinning();
        let thread = self
            .thread
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .take();
        match thread {
            None => Ok(()),
            Some(thread) => join_executor(thread),
        }
    }
}

impl Drop for RosSensorRuntime {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

fn spawn_spin(executor: Executor) -> Result<JoinHandle<Vec<RclrsError>>, SensorClientError> {
    thread::Builder::new()
        .name("ros-sensor-client-executor".into())
        .spawn(move || spin(executor))
        .map_err(|error| SensorClientError::Ros(format!("could not start ROS executor: {error}")))
}

fn spin(mut executor: Executor) -> Vec<RclrsError> {
    executor.spin(SpinOptions::default())
}

fn await_ready(ready_rx: &mpsc::Receiver<()>) -> Result<(), SensorClientError> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    loop {
        match ready_rx.try_recv() {
            Ok(()) => return Ok(()),
            Err(TryRecvError::Disconnected) => {
                return Err(SensorClientError::Ros(
                    "ROS executor readiness callback was dropped".into(),
                ));
            }
            Err(TryRecvError::Empty) => {}
        }
        if Instant::now() >= deadline {
            return Err(SensorClientError::Ros(
                "ROS executor readiness timed out".into(),
            ));
        }
        thread::sleep(STARTUP_POLL_INTERVAL);
    }
}

fn join_executor(thread: JoinHandle<Vec<RclrsError>>) -> Result<(), SensorClientError> {
    match thread.join() {
        Err(_) => Err(SensorClientError::ExecutorPanicked),
        Ok(errors) if errors.is_empty() => Ok(()),
        Ok(errors) => {
            let details = errors
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
                .join("; ");
            Err(SensorClientError::Ros(format!(
                "ROS executor stopped with errors: {details}"
            )))
        }
    }
}
