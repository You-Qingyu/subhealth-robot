use std::path::PathBuf;

use ros_task_client::{DeviceConfig, RosRuntimeConfig, RosTaskClientConfig, RosTaskError};

fn valid_config() -> RosTaskClientConfig {
    RosTaskClientConfig {
        version: 1,
        ros: RosRuntimeConfig {
            node_name: "control_plane_server".into(),
            feedback_buffer: 16,
            server_wait_timeout_ms: 2_000,
        },
        devices: vec![DeviceConfig {
            id: "mock_exec".into(),
            action_name: "/mock_exec/execute_task".into(),
            enabled: true,
        }],
    }
}

#[test]
fn valid_static_registry_configuration_is_accepted() {
    assert!(valid_config().validate().is_ok());
}

#[test]
fn repository_sample_configuration_is_loaded() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../config/devices.yaml");
    let config = RosTaskClientConfig::from_path(&path).unwrap();

    assert_eq!(
        config,
        RosTaskClientConfig {
            version: 1,
            ros: RosRuntimeConfig {
                node_name: "execution".into(),
                feedback_buffer: 64,
                server_wait_timeout_ms: 5_000,
            },
            devices: vec![DeviceConfig {
                id: "mock_exec".into(),
                action_name: "/mock_exec/execute_task".into(),
                enabled: true,
            }],
        }
    );
}

#[test]
fn duplicate_device_ids_and_action_names_are_rejected() {
    let mut ids = valid_config();
    ids.devices.push(DeviceConfig {
        id: "mock_exec".into(),
        action_name: "/other/task".into(),
        enabled: true,
    });
    assert!(matches!(
        ids.validate(),
        Err(RosTaskError::InvalidConfig {
            field: "device_id",
            ..
        })
    ));

    let mut names = valid_config();
    names.devices.push(DeviceConfig {
        id: "other".into(),
        action_name: "/mock_exec/execute_task".into(),
        enabled: true,
    });
    assert!(matches!(
        names.validate(),
        Err(RosTaskError::InvalidConfig {
            field: "action_name",
            ..
        })
    ));
}

#[test]
fn unsupported_version_empty_names_zero_buffer_and_zero_timeout_are_rejected() {
    let mut version = valid_config();
    version.version = 2;
    assert_invalid_field(version.validate(), "version");

    let mut node = valid_config();
    node.ros.node_name.clear();
    assert_invalid_field(node.validate(), "node_name");
    let mut device = valid_config();
    device.devices[0].id.clear();
    assert_invalid_field(device.validate(), "device_id");
    let mut action = valid_config();
    action.devices[0].action_name.clear();
    assert_invalid_field(action.validate(), "action_name");
    let mut buffer = valid_config();
    buffer.ros.feedback_buffer = 0;
    assert_invalid_field(buffer.validate(), "feedback_buffer");
    let mut timeout = valid_config();
    timeout.ros.server_wait_timeout_ms = 0;
    assert_invalid_field(timeout.validate(), "server_wait_timeout_ms");
}

#[test]
fn leading_and_trailing_whitespace_in_names_is_rejected() {
    let mut node_leading = valid_config();
    node_leading.ros.node_name.insert(0, ' ');
    assert_invalid_field(node_leading.validate(), "node_name");

    let mut node_trailing = valid_config();
    node_trailing.ros.node_name.push(' ');
    assert_invalid_field(node_trailing.validate(), "node_name");

    let mut device_leading = valid_config();
    device_leading.devices[0].id.insert(0, '\t');
    assert_invalid_field(device_leading.validate(), "device_id");

    let mut device_trailing = valid_config();
    device_trailing.devices[0].id.push('\n');
    assert_invalid_field(device_trailing.validate(), "device_id");

    let mut action_leading = valid_config();
    action_leading.devices[0].action_name.insert(0, ' ');
    assert_invalid_field(action_leading.validate(), "action_name");

    let mut action_trailing = valid_config();
    action_trailing.devices[0].action_name.push('\t');
    assert_invalid_field(action_trailing.validate(), "action_name");
}

#[test]
fn action_names_must_be_canonical_absolute_names() {
    for invalid in [
        "/",
        "/bad-name",
        "/foo bar",
        "/1device/execute_task",
        "/device/execute.task",
        "/device/{execute_task}",
        "mock_exec/execute_task",
        "/mock_exec/execute_task/",
        "/mock_exec//execute_task",
    ] {
        let mut config = valid_config();
        config.devices[0].action_name = invalid.into();
        assert_invalid_field(config.validate(), "action_name");
    }
}

#[test]
fn valid_canonical_action_names_follow_ros_graph_name_grammar() {
    for valid in [
        "/mock_exec/execute_task",
        "/_mock_exec/execute_task_2",
        "/mock_exec_2/_execute_task",
    ] {
        let mut config = valid_config();
        config.devices[0].action_name = valid.into();
        assert!(config.validate().is_ok(), "{valid} should be valid");
    }
}

fn assert_invalid_field(result: Result<(), RosTaskError>, expected_field: &'static str) {
    assert!(matches!(
        result,
        Err(RosTaskError::InvalidConfig {
            field,
            message: _,
        }) if field == expected_field
    ));
}
