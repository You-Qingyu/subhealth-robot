//! 由运行时组合根拥有的具体 ROS 执行实现。
//!
//! 本 crate 实现 [`orchestration::ExecutionPort`]，并将 canonical
//! [`platform::Task`] 委托给 [`ros_task_client::RosTaskClient`]。

use std::{future::Future, pin::Pin};

use orchestration::ExecutionPort;
use platform::{ExecutionError, ExecutionSession, Task};
use ros_task_client::{RosTaskClient, RosTaskRuntime};

/// 使用 ROS task client 执行任务的具体执行服务。
pub struct Execution {
    client: RosTaskClient,
    runtime: RosTaskRuntime,
}

impl Execution {
    /// 从 `ROS_TASK_CLIENT_CONFIG` 初始化 ROS 执行服务。
    ///
    /// # 错误
    ///
    /// 配置无效、ROS context 无法创建或 executor 无法启动时返回错误。
    pub fn init() -> Result<Self, ExecutionError> {
        let (client, runtime) =
            RosTaskClient::init().map_err(|error| ExecutionError::Failed(error.to_string()))?;
        Ok(Self { client, runtime })
    }

    /// 请求 ROS executor 停止。
    pub fn shutdown(&self) -> Result<(), ExecutionError> {
        self.runtime
            .shutdown()
            .map_err(|error| ExecutionError::Failed(error.to_string()))
    }
}

impl ExecutionPort for Execution {
    fn validate<'a>(
        &'a self,
        task: &'a Task,
    ) -> Pin<Box<dyn Future<Output = Result<(), ExecutionError>> + Send + 'a>> {
        Box::pin(async move {
            self.client
                .validate(task)
                .await
                .map_err(ExecutionError::from)
        })
    }

    fn execute(
        &self,
        task: Task,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionSession, ExecutionError>> + Send + '_>> {
        Box::pin(self.client.execute(task))
    }
}
