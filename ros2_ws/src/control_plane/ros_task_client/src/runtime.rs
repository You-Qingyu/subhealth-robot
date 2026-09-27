use std::{
    panic::{catch_unwind, AssertUnwindSafe},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Condvar, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use rclrs::{Executor, ExecutorCommands, RclrsError, SpinOptions};
use tokio::sync::watch;

use crate::RosTaskError;

/// 在独立线程中运行 ROS executor，并协调 client shutdown。
pub struct RosTaskRuntime {
    commands: Arc<ExecutorCommands>,
    stopping: Arc<AtomicBool>,
    shutdown_tx: watch::Sender<bool>,
    shutdown: ShutdownCoordinator,
    #[cfg(test)]
    panic_before_halt_notice: Option<mpsc::Sender<()>>,
}

const STARTUP_TIMEOUT: Duration = Duration::from_secs(5);
const STARTUP_POLL_INTERVAL: Duration = Duration::from_millis(10);

enum ExecutorExit {
    Returned,
    Panicked,
}

impl RosTaskRuntime {
    /// 启动 ROS executor 线程，并等待其 readiness callback 完成。
    ///
    /// # 错误
    ///
    /// executor 线程无法启动、启动期间退出、panic 或超过 readiness 超时时间
    /// 时返回 [`RosTaskError`]。
    pub fn start(
        executor: Executor,
        stopping: Arc<AtomicBool>,
        shutdown_tx: watch::Sender<bool>,
    ) -> Result<Self, RosTaskError> {
        Self::start_with_spin(executor, stopping, shutdown_tx, |mut executor| {
            executor.spin(SpinOptions::default())
        })
    }

    fn start_with_spin<F>(
        executor: Executor,
        stopping: Arc<AtomicBool>,
        shutdown_tx: watch::Sender<bool>,
        spin: F,
    ) -> Result<Self, RosTaskError>
    where
        F: FnOnce(Executor) -> Vec<RclrsError> + Send + 'static,
    {
        let commands = Arc::clone(executor.commands());
        let (ready_tx, ready_rx) = mpsc::channel();
        drop(commands.run(async move {
            let _ = ready_tx.send(());
        }));
        let (exit_tx, exit_rx) = mpsc::channel();

        let thread = thread::Builder::new()
            .name("ros-task-client-executor".into())
            .spawn(
                move || match catch_unwind(AssertUnwindSafe(|| spin(executor))) {
                    Ok(errors) => {
                        let _ = exit_tx.send(ExecutorExit::Returned);
                        errors
                    }
                    Err(payload) => {
                        let _ = exit_tx.send(ExecutorExit::Panicked);
                        std::panic::resume_unwind(payload)
                    }
                },
            )
            .map_err(|error| RosTaskError::Ros(format!("could not start ROS executor: {error}")))?;

        let deadline = Instant::now() + STARTUP_TIMEOUT;
        loop {
            match ready_rx.try_recv() {
                Ok(()) => break,
                Err(mpsc::TryRecvError::Disconnected) => {
                    return Err(join_failed_startup(
                        commands,
                        thread,
                        "readiness callback was dropped",
                    ));
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }

            match exit_rx.try_recv() {
                Ok(ExecutorExit::Returned) => {
                    return Err(join_failed_startup(
                        commands,
                        thread,
                        "executor stopped during startup",
                    ));
                }
                Ok(ExecutorExit::Panicked) => {
                    return Err(join_failed_startup(
                        commands,
                        thread,
                        "executor panicked during startup",
                    ));
                }
                Err(mpsc::TryRecvError::Disconnected | mpsc::TryRecvError::Empty) => {}
            }

            if Instant::now() >= deadline {
                return Err(join_failed_startup(
                    commands,
                    thread,
                    "executor readiness timed out",
                ));
            }
            thread::sleep(STARTUP_POLL_INTERVAL);
        }

        Ok(Self {
            commands,
            stopping,
            shutdown_tx,
            shutdown: ShutdownCoordinator::new(thread),
            #[cfg(test)]
            panic_before_halt_notice: None,
        })
    }

    /// 请求 executor 停止，并等待其线程完成。
    ///
    /// 多次调用是安全的；如果 ROS executor 或 shutdown 协调过程失败，返回
    /// [`RosTaskError`]。
    pub fn shutdown(&self) -> Result<(), RosTaskError> {
        self.shutdown
            .shutdown(|| {
                self.stopping.store(true, Ordering::Release);
                let relay_panicked = catch_unwind(AssertUnwindSafe(|| {
                    let _ = self.shutdown_tx.send(true);
                }))
                .is_err();
                let halt_panicked = catch_unwind(AssertUnwindSafe(|| {
                    #[cfg(test)]
                    if let Some(notice) = &self.panic_before_halt_notice {
                        let _ = notice.send(());
                        panic!("injected panic during shutdown signal");
                    }
                    self.commands.halt_spinning();
                }))
                .is_err();
                relay_panicked || halt_panicked
            })
            .into_result()
    }
}

fn join_failed_startup(
    commands: Arc<ExecutorCommands>,
    thread: JoinHandle<Vec<RclrsError>>,
    reason: &str,
) -> RosTaskError {
    commands.halt_spinning();
    match thread.join() {
        Err(_) => RosTaskError::ExecutorPanicked,
        Ok(errors) if errors.is_empty() => RosTaskError::Ros(format!("ROS executor {reason}")),
        Ok(errors) => {
            RosTaskError::Ros(format!("ROS executor {reason}: {}", format_errors(errors)))
        }
    }
}

impl Drop for RosTaskRuntime {
    fn drop(&mut self) {
        drop(catch_unwind(AssertUnwindSafe(|| {
            let _ = self.shutdown();
        })));
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum ShutdownOutcome {
    Complete,
    ExecutorPanicked,
    Ros(String),
}

impl ShutdownOutcome {
    fn into_result(self) -> Result<(), RosTaskError> {
        match self {
            Self::Complete => Ok(()),
            Self::ExecutorPanicked => Err(RosTaskError::ExecutorPanicked),
            Self::Ros(message) => Err(RosTaskError::Ros(message)),
        }
    }
}

enum ShutdownState {
    Running(Option<JoinHandle<Vec<RclrsError>>>),
    Joining { synchronization_failed: bool },
    Complete(ShutdownOutcome),
}

struct ShutdownCoordinator {
    state: Mutex<ShutdownState>,
    completed: Condvar,
    #[cfg(test)]
    waiter_notice: Option<mpsc::Sender<()>>,
}

impl ShutdownCoordinator {
    fn new(thread: JoinHandle<Vec<RclrsError>>) -> Self {
        Self {
            state: Mutex::new(ShutdownState::Running(Some(thread))),
            completed: Condvar::new(),
            #[cfg(test)]
            waiter_notice: None,
        }
    }

    #[cfg(test)]
    fn new_for_test(thread: JoinHandle<Vec<RclrsError>>, waiter_notice: mpsc::Sender<()>) -> Self {
        Self {
            state: Mutex::new(ShutdownState::Running(Some(thread))),
            completed: Condvar::new(),
            waiter_notice: Some(waiter_notice),
        }
    }

    fn shutdown(&self, signal_shutdown: impl FnOnce() -> bool) -> ShutdownOutcome {
        let state_result = self.state.lock();
        let mut synchronization_failed = state_result.is_err();
        let mut state = state_result.unwrap_or_else(std::sync::PoisonError::into_inner);

        let thread = loop {
            match &mut *state {
                ShutdownState::Running(thread) => {
                    let Some(thread) = thread.take() else {
                        let outcome = ShutdownOutcome::ExecutorPanicked;
                        *state = ShutdownState::Complete(outcome.clone());
                        self.completed.notify_all();
                        return outcome;
                    };
                    *state = ShutdownState::Joining {
                        synchronization_failed,
                    };
                    break thread;
                }
                ShutdownState::Joining {
                    synchronization_failed: shared_failure,
                } => {
                    *shared_failure |= synchronization_failed;
                    #[cfg(test)]
                    if let Some(notice) = &self.waiter_notice {
                        let _ = notice.send(());
                    }
                    let wait_result = self.completed.wait(state);
                    synchronization_failed |= wait_result.is_err();
                    state = wait_result.unwrap_or_else(std::sync::PoisonError::into_inner);
                }
                ShutdownState::Complete(outcome) => return outcome.clone(),
            }
        };
        drop(state);

        let signal_failed = catch_unwind(AssertUnwindSafe(signal_shutdown)).unwrap_or(true);
        let mut outcome = catch_unwind(AssertUnwindSafe(|| match thread.join() {
            Err(_) => ShutdownOutcome::ExecutorPanicked,
            Ok(errors) if errors.is_empty() => ShutdownOutcome::Complete,
            Ok(errors) => ShutdownOutcome::Ros(format_errors(errors)),
        }))
        .unwrap_or(ShutdownOutcome::ExecutorPanicked);

        let state_result = self.state.lock();
        synchronization_failed |= state_result.is_err();
        let mut state = state_result.unwrap_or_else(std::sync::PoisonError::into_inner);
        if let ShutdownState::Joining {
            synchronization_failed: shared_failure,
        } = &*state
        {
            synchronization_failed |= *shared_failure;
        }
        if signal_failed || synchronization_failed {
            outcome = ShutdownOutcome::ExecutorPanicked;
        }
        *state = ShutdownState::Complete(outcome.clone());
        self.completed.notify_all();
        outcome
    }
}

fn format_errors(errors: Vec<RclrsError>) -> String {
    errors
        .into_iter()
        .map(|error| error.to_string())
        .collect::<Vec<_>>()
        .join("; ")
}

#[cfg(test)]
mod tests {
    use std::{
        panic::{catch_unwind, AssertUnwindSafe},
        sync::{atomic::AtomicBool, mpsc, Arc},
        thread,
        time::Duration,
    };

    use rclrs::CreateBasicExecutor;
    use tokio::sync::watch;

    use super::{RosTaskRuntime, ShutdownCoordinator, ShutdownOutcome};

    fn runtime_with_worker(
        worker: thread::JoinHandle<Vec<rclrs::RclrsError>>,
        panic_before_halt_notice: Option<mpsc::Sender<()>>,
    ) -> RosTaskRuntime {
        let context = rclrs::Context::default_from_env().unwrap();
        let executor = context.create_basic_executor();
        let commands = Arc::clone(executor.commands());
        let (shutdown_tx, _shutdown_rx) = watch::channel(false);

        RosTaskRuntime {
            commands,
            stopping: Arc::new(AtomicBool::new(false)),
            shutdown_tx,
            shutdown: ShutdownCoordinator::new(worker),
            panic_before_halt_notice,
        }
    }

    #[test]
    fn startup_returns_when_executor_stops_before_readiness() {
        let context = rclrs::Context::default_from_env().unwrap();
        let executor = context.create_basic_executor();
        let (shutdown_tx, _shutdown_rx) = watch::channel(false);

        let result = RosTaskRuntime::start_with_spin(
            executor,
            Arc::new(AtomicBool::new(false)),
            shutdown_tx,
            |_executor| Vec::new(),
        );

        assert!(matches!(
            result,
            Err(crate::RosTaskError::Ros(message))
                if message.contains("startup") || message.contains("readiness")
        ));
    }

    #[test]
    fn concurrent_callers_wait_for_and_observe_the_same_terminal_outcome() {
        let (release_tx, release_rx) = mpsc::channel();
        let worker = thread::spawn(move || -> Vec<rclrs::RclrsError> {
            release_rx
                .recv_timeout(Duration::from_secs(5))
                .expect("worker release timed out");
            panic!("injected worker panic");
        });
        let (waiter_tx, waiter_rx) = mpsc::channel();
        let coordinator = Arc::new(ShutdownCoordinator::new_for_test(worker, waiter_tx));
        let (leader_started_tx, leader_started_rx) = mpsc::channel();
        let (leader_done_tx, leader_done_rx) = mpsc::channel();
        let leader_coordinator = Arc::clone(&coordinator);
        let leader = thread::spawn(move || {
            let outcome = leader_coordinator.shutdown(|| {
                leader_started_tx.send(()).unwrap();
                false
            });
            leader_done_tx.send(outcome).unwrap();
        });
        leader_started_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown leader did not start");

        let (follower_done_tx, follower_done_rx) = mpsc::channel();
        let follower_coordinator = Arc::clone(&coordinator);
        let follower = thread::spawn(move || {
            let outcome = follower_coordinator.shutdown(|| {
                panic!("a follower must not signal shutdown");
            });
            follower_done_tx.send(outcome).unwrap();
        });
        waiter_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown follower did not wait");
        assert!(matches!(
            follower_done_rx.try_recv(),
            Err(mpsc::TryRecvError::Empty)
        ));

        release_tx.send(()).unwrap();
        let leader_outcome = leader_done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown leader did not finish");
        let follower_outcome = follower_done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown follower did not finish");

        assert_eq!(leader_outcome, ShutdownOutcome::ExecutorPanicked);
        assert_eq!(follower_outcome, leader_outcome);
        leader.join().unwrap();
        follower.join().unwrap();
    }

    #[test]
    fn drop_contains_signal_panic_and_still_waits_for_join() {
        let (release_tx, release_rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            release_rx
                .recv_timeout(Duration::from_secs(5))
                .expect("worker release timed out");
            Vec::new()
        });
        let (panic_notice_tx, panic_notice_rx) = mpsc::channel();
        let runtime = runtime_with_worker(worker, Some(panic_notice_tx));
        let (done_tx, done_rx) = mpsc::channel();

        let drop_thread = thread::spawn(move || {
            let did_not_unwind = catch_unwind(AssertUnwindSafe(|| drop(runtime))).is_ok();
            let _ = done_tx.send(did_not_unwind);
        });

        panic_notice_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown signal panic was not injected");
        assert!(matches!(done_rx.try_recv(), Err(mpsc::TryRecvError::Empty)));
        release_tx.send(()).unwrap();
        assert!(done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("runtime destructor timed out"));
        drop_thread.join().unwrap();
    }

    #[test]
    fn explicit_shutdown_reports_signal_panic_after_join() {
        let (release_tx, release_rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            release_rx
                .recv_timeout(Duration::from_secs(5))
                .expect("worker release timed out");
            Vec::new()
        });
        let (panic_notice_tx, panic_notice_rx) = mpsc::channel();
        let runtime = runtime_with_worker(worker, Some(panic_notice_tx));
        let (done_tx, done_rx) = mpsc::channel();

        let shutdown_thread = thread::spawn(move || {
            let first = runtime.shutdown();
            let second = runtime.shutdown();
            let _ = done_tx.send((first, second));
        });

        panic_notice_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("shutdown signal panic was not injected");
        assert!(matches!(done_rx.try_recv(), Err(mpsc::TryRecvError::Empty)));
        release_tx.send(()).unwrap();
        let (first, second) = done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("explicit shutdown timed out");
        assert!(matches!(first, Err(crate::RosTaskError::ExecutorPanicked)));
        assert_eq!(second, first);
        shutdown_thread.join().unwrap();
    }

    #[test]
    fn drop_recovers_poisoned_coordinator_and_worker_panic() {
        let (release_tx, release_rx) = mpsc::channel();
        let worker = thread::spawn(move || -> Vec<rclrs::RclrsError> {
            release_rx
                .recv_timeout(Duration::from_secs(5))
                .expect("worker release timed out");
            panic!("injected worker panic");
        });
        let runtime = runtime_with_worker(worker, None);
        let poison_result = catch_unwind(AssertUnwindSafe(|| {
            let _state = runtime.shutdown.state.lock().unwrap();
            panic!("poison shutdown coordinator");
        }));
        assert!(poison_result.is_err());
        let (done_tx, done_rx) = mpsc::channel();

        let drop_thread = thread::spawn(move || {
            let did_not_unwind = catch_unwind(AssertUnwindSafe(|| drop(runtime))).is_ok();
            let _ = done_tx.send(did_not_unwind);
        });

        assert!(matches!(done_rx.try_recv(), Err(mpsc::TryRecvError::Empty)));
        release_tx.send(()).unwrap();
        assert!(done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("runtime destructor timed out"));
        drop_thread.join().unwrap();
    }
}
