use std::{
    sync::{mpsc, Arc, Barrier},
    thread,
    time::Duration,
};

use platform::{DeviceId, ExecutionError, ExecutionSession, Primitive, Task, TaskId};
use ros_task_client::{
    DeviceConfig, RosRuntimeConfig, RosTaskClient, RosTaskClientConfig, RosTaskError,
};
use tokio_stream::StreamExt;

fn config(test_name: &str) -> RosTaskClientConfig {
    RosTaskClientConfig {
        version: 1,
        ros: RosRuntimeConfig {
            node_name: format!("ros_task_client_{test_name}_{}", std::process::id()),
            feedback_buffer: 8,
            server_wait_timeout_ms: 100,
        },
        devices: vec![DeviceConfig {
            id: "mock_exec".into(),
            action_name: "/mock_exec/execute_task".into(),
            enabled: true,
        }],
    }
}

#[test]
fn immediate_shutdown_is_bounded_and_idempotent() {
    let (_client, runtime) = RosTaskClient::init_with_config(config("lifecycle")).unwrap();
    let (done_tx, done_rx) = mpsc::channel();

    let shutdown_thread = thread::spawn(move || {
        let first = runtime.shutdown();
        let second = runtime.shutdown();
        let _ = done_tx.send((first, second));
    });

    let (first, second) = done_rx
        .recv_timeout(Duration::from_secs(5))
        .expect("immediate shutdown timed out");
    first.unwrap();
    second.unwrap();
    shutdown_thread.join().unwrap();
}

#[test]
fn concurrent_shutdown_calls_are_bounded() {
    let (_client, runtime) = RosTaskClient::init_with_config(config("concurrent")).unwrap();
    let runtime = Arc::new(runtime);
    let barrier = Arc::new(Barrier::new(5));
    let (done_tx, done_rx) = mpsc::channel();

    let threads: Vec<_> = (0..4)
        .map(|_| {
            let runtime = Arc::clone(&runtime);
            let barrier = Arc::clone(&barrier);
            let done_tx = done_tx.clone();
            thread::spawn(move || {
                barrier.wait();
                let _ = done_tx.send(runtime.shutdown());
            })
        })
        .collect();
    barrier.wait();

    for _ in 0..4 {
        done_rx
            .recv_timeout(Duration::from_secs(5))
            .expect("concurrent shutdown timed out")
            .unwrap();
    }
    for thread in threads {
        thread.join().unwrap();
    }
}

#[test]
fn init_with_config_rejects_invalid_config_before_starting_executor() {
    let mut config = config("invalid");
    config.ros.feedback_buffer = 0;

    assert!(matches!(
        RosTaskClient::init_with_config(config),
        Err(RosTaskError::InvalidConfig {
            field: "feedback_buffer",
            ..
        })
    ));
}

#[tokio::test(flavor = "multi_thread")]
async fn unknown_device_returns_without_waiting_for_action_graph() {
    let (client, runtime) = RosTaskClient::init_with_config(config("unknown_device")).unwrap();
    let outcome = tokio::time::timeout(
        Duration::from_millis(50),
        client.execute(Task {
            id: TaskId("unknown-device".into()),
            device_id: DeviceId("not_configured".into()),
            primitive: Primitive::GoToTag,
            target: vec![7],
            deadline_ms: None,
        }),
    )
    .await
    .expect("unknown device lookup waited unexpectedly");

    assert!(matches!(
        outcome,
        Err(ExecutionError::Failed(message)) if message == "unknown device: not_configured"
    ));
    runtime.shutdown().unwrap();
}

#[tokio::test(flavor = "multi_thread")]
async fn absent_action_server_returns_after_configured_timeout() {
    let mut missing = config("absent_server");
    missing.devices[0].action_name = "/missing/execute_task".into();
    missing.ros.server_wait_timeout_ms = 100;
    let (client, runtime) = RosTaskClient::init_with_config(missing.clone()).unwrap();
    let started = std::time::Instant::now();

    let server_wait_timeout = Duration::from_millis(missing.ros.server_wait_timeout_ms);
    let upper_bound = server_wait_timeout + Duration::from_secs(1);
    let outcome = tokio::time::timeout(
        upper_bound,
        client.execute(Task {
            id: TaskId("absent-server".into()),
            device_id: DeviceId("mock_exec".into()),
            primitive: Primitive::GoToTag,
            target: vec![7],
            deadline_ms: None,
        }),
    )
    .await
    .expect("unavailable action server wait exceeded its upper bound");

    assert!(started.elapsed() >= server_wait_timeout);
    assert!(started.elapsed() < upper_bound);
    assert!(matches!(
        outcome,
        Err(ExecutionError::Failed(message))
            if message == "action server unavailable for device mock_exec at /missing/execute_task"
    ));
    runtime.shutdown().unwrap();
}

#[tokio::test(flavor = "multi_thread")]
async fn execute_after_shutdown_returns_shutdown() {
    let (client, runtime) =
        RosTaskClient::init_with_config(config("execute_after_shutdown")).unwrap();
    runtime.shutdown().unwrap();

    let outcome = tokio::time::timeout(
        Duration::from_secs(1),
        client.execute(Task {
            id: TaskId("after-shutdown".into()),
            device_id: DeviceId("mock_exec".into()),
            primitive: Primitive::GoToTag,
            target: vec![7],
            deadline_ms: None,
        }),
    )
    .await
    .expect("execute after shutdown did not return");

    assert!(
        matches!(outcome, Err(ExecutionError::Failed(message)) if message == "ROS task client is shutting down")
    );
}

#[test]
fn dropping_client_before_explicit_shutdown_still_allows_join() {
    let (client, runtime) = RosTaskClient::init_with_config(config("drop_client")).unwrap();
    drop(client);
    runtime.shutdown().unwrap();
}

#[tokio::test(flavor = "multi_thread")]
#[ignore = "requires running mock_exec_layer"]
async fn runtime_shutdown_resolves_outstanding_result() {
    let (client, runtime) = RosTaskClient::init_with_config(config("shutdown_result")).unwrap();
    let ExecutionSession {
        mut feedback,
        result,
        ..
    } = tokio::time::timeout(
        Duration::from_secs(3),
        client.execute(Task {
            id: TaskId("shutdown-result".into()),
            device_id: DeviceId("mock_exec".into()),
            primitive: Primitive::GoToTag,
            target: vec![7],
            deadline_ms: None,
        }),
    )
    .await
    .expect("shutdown-result execute timed out")
    .unwrap();

    tokio::time::timeout(Duration::from_secs(3), feedback.next())
        .await
        .expect("shutdown-result feedback timed out")
        .unwrap()
        .unwrap();
    runtime.shutdown().unwrap();
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(3), result)
            .await
            .expect("shutdown-result result timed out"),
        Err(ExecutionError::Failed(
            "ROS task client is shutting down".into()
        ))
    );
}
