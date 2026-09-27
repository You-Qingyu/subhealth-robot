use rclrs::GoalStatusCode;
use ros_env::task_interfaces::action::{
    ExecuteTask_Feedback, ExecuteTask_Goal, ExecuteTask_Result,
};
use serde::Serialize;

use platform::{ExecutionFeedback, ExecutionResult, Primitive, Task, TaskId};

use crate::RosTaskError;

#[derive(Serialize)]
struct GoToTagPayload<'a> {
    target_tags: &'a [i32],
}

pub fn to_ros_goal(command: &Task) -> Result<ExecuteTask_Goal, RosTaskError> {
    let deadline_unix_ms = command
        .deadline_ms
        .map(i64::try_from)
        .transpose()
        .map_err(|_| RosTaskError::InvalidCommand {
            field: "deadline_ms",
            message: "must fit the ROS int64 deadline".into(),
        })?
        .unwrap_or(0);
    let primitive = match command.primitive {
        Primitive::GoToTag => "go_to_tag",
    };
    let payload_json = serde_json::to_string(&GoToTagPayload {
        target_tags: &command.target,
    })
    .map_err(|error| mapping_error("target", error.to_string()))?;
    Ok(ExecuteTask_Goal {
        task_id: command.id.0.clone(),
        device_id: command.device_id.0.clone(),
        primitive: primitive.into(),
        payload_json,
        deadline_unix_ms,
    })
}

pub fn from_ros_feedback(
    expected_task_id: &str,
    raw: ExecuteTask_Feedback,
) -> Result<ExecutionFeedback, RosTaskError> {
    validate_task_id(expected_task_id, &raw.task_id)?;
    if !raw.progress.is_finite() || !(0.0..=1.0).contains(&raw.progress) {
        return Err(mapping_error(
            "progress",
            "must be finite and in [0.0, 1.0]",
        ));
    }
    Ok(ExecutionFeedback {
        task_id: TaskId(raw.task_id),
        progress: raw.progress,
        phase: raw.phase,
    })
}

pub fn from_ros_result(
    expected_task_id: &str,
    status: GoalStatusCode,
    raw: ExecuteTask_Result,
) -> Result<ExecutionResult, RosTaskError> {
    validate_task_id(expected_task_id, &raw.task_id)?;
    let state = match (status, raw.final_state.as_str()) {
        (GoalStatusCode::Succeeded, "succeeded") => "succeeded",
        (GoalStatusCode::Aborted, "failed") => "failed",
        (status, state) => {
            return Err(mapping_error(
                "final_state",
                format!("unsupported ROS status/final state pair: {status:?}/{state}"),
            ))
        }
    };
    Ok(ExecutionResult {
        task_id: TaskId(raw.task_id),
        state: state.into(),
    })
}

fn validate_task_id(expected: &str, actual: &str) -> Result<(), RosTaskError> {
    if actual != expected || actual.is_empty() {
        return Err(mapping_error(
            "task_id",
            format!("expected `{expected}`, got `{actual}`"),
        ));
    }
    Ok(())
}

fn mapping_error(field: &'static str, message: impl Into<String>) -> RosTaskError {
    RosTaskError::Mapping {
        field,
        message: message.into(),
    }
}
