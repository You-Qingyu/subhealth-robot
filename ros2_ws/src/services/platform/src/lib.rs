//! 设备无关的控制平面类型和模块接口。
//!
//! 本 crate 定义任务、执行、传感器和事件在服务之间共享的 canonical 类型。
//! HTTP、ROS 和具体设备实现应在各自 seam 显式映射到这些类型。

pub mod domain;
pub mod event;
pub mod execution;
pub mod repository;
pub mod sensor;
pub mod task;

pub use domain::{DeviceDescriptor, DeviceId, DeviceState, SensorId, TaskId};
pub use event::{EventSequence, SystemEvent};
pub use execution::{
    ExecutionError, ExecutionFeedback, ExecutionFeedbackStream, ExecutionResult,
    ExecutionResultFuture, ExecutionSession,
};
pub use repository::{TaskRepository, TaskRepositoryError};
pub use sensor::{SensorDescriptor, SensorFilter, SensorProvider, SensorSample, SensorStream};
pub use task::{Primitive, Task, TaskRecord, TaskState};
