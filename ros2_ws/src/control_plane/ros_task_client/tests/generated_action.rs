use ros_env::task_interfaces::action::{
    ExecuteTask, ExecuteTask_Feedback, ExecuteTask_Goal, ExecuteTask_Result,
};
use rosidl_runtime_rs::Action;

fn assert_action<A: Action>() {}

#[test]
fn execute_task_has_generated_rust_action_types() {
    assert_action::<ExecuteTask>();
    let _: <ExecuteTask as Action>::Goal = ExecuteTask_Goal::default();
    let _: <ExecuteTask as Action>::Feedback = ExecuteTask_Feedback::default();
    let _: <ExecuteTask as Action>::Result = ExecuteTask_Result::default();
}
