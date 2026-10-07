# TonyPi 执行 endpoint

## 运行边界

`tonypi_exec_layer` 是运行在 TonyPi 真机上的 ROS 2 action endpoint。控制平面仍然运行在笔记本，通过 `ExecuteTask` action 与真机通信。

真机不需要 Rust、`rustup` 或 Cargo，只构建 `task_interfaces` 和 `tonypi_exec_layer` 两个 ROS 包。

## 真机环境

真机使用 ROS Jazzy、Cyclone DDS 和 domain `1`：

```bash
export ROS_DOMAIN_ID=1
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export TONYPI_ROOT=/home/pi/TonyPi
```

`TONYPI_ROOT` 默认是 `/home/pi/TonyPi`；真机当前也提供指向 `/home/ubuntu/TonyPi` 的软链接。

## 构建和启动

在真机上的仓库副本中执行：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to task_interfaces tonypi_exec_layer --symlink-install
source install/setup.bash
make run endpoint DEVICE_TYPE=tonypi
```

启动 endpoint 会初始化 TonyPi SDK 和串口，但不会主动调用动作组。收到合法 goal 后才可能让机器人运动。

## AprilTag 闭环导航

endpoint 只接受 `go_to_tag`，`target_tags` 是按顺序到达的 AprilTag ID，不把
Tag ID 映射为固定动作。导航按当前观测执行有限动作，并在动作结束后重新观测；
目标不可见时先保持机身静止转头寻找；云台扫完仍未发现时才逐步原地转体，
每步之后重新观测。完整的状态、阈值、调用顺序和异常语义见
[TonyPi `go_to_tag` 状态机说明](../../specs/tonypi-go-to-tag-state-machine.md)。

前进动作轮流使用 `go_forward_one_step_left.d6a` 和
`go_forward_one_step_right.d6a`。启动 endpoint 前，必须将这两个文件放入
`TONYPI_ROOT/ActionGroups/`；启动时缺少任一必需动作组会报错，不会回退到
原始 `go_forward_one_step.d6a`。

每次用于决策的 `observe_tags()` 都在真机上保存逐帧回放。日志中的
`tonypi_replay directory=...` 给出本次任务的目录，默认为
`/tmp/tonypi-replays/<随机任务目录>`，可通过 ROS 参数 `replay_directory` 修改。
直接用浏览器打开其中的 `index.html` 可逐帧浏览或播放，帧旁的关键观测和动作
信息已写入页面，不需要本地 HTTP 服务，也可查看同名 JSON 中的完整记录和原始图片；
回放目录中的标注图用于查看相机画面，`raw/` 保存识别所用的原图。

## AprilTag 位姿观测（离线、只读）

图像采集与位姿测量入口都与运动 endpoint 独立，均不导入 `ActionGroupControl`
或发送动作。`tonypi_capture_frame` 从指定 V4L2 设备读取有限帧，保存一张未经
处理的原图；要求运行用户属于 `video` 组、重新登录后具有 `/dev/video0` 的
读取权限，且摄像头未被其他进程独占。

`tonypi_observe_tag` 只读取本地图片和
`TONYPI_ROOT/Functions/CameraCalibration/calibration_param.npz`，不会打开摄像头、
导入运动 SDK。真机需有 `python3-opencv`、`python3-numpy`。
更新代码并构建 ROS 包后，使用与标定一致、**未缩放及未去畸变**的 640×480
相机原图：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run tonypi_exec_layer tonypi_capture_frame /tmp/tag-1-50cm.png
ros2 run tonypi_exec_layer tonypi_observe_tag \
  --tag-id 1 --family 36h11 /tmp/tag-1-50cm.png
```

当前使用的实物标签为 `36h11`、边长 10 cm；示例中的 ID 应替换为实际要观测
的标签 ID。
`--family` 必须填写实物标签的 family（支持 `16h5`、`25h9`、`36h10`、`36h11`）；
不能只凭 Tag ID 推断。每张图片输出一行 JSON：`pose=null` 表示目标未检出；
`distance_m` 是相机到 10 cm Tag 中心的三维直线距离，`forward_m`、
`lateral_m`、`vertical_m` 是相机坐标系分量，`bearing_deg` 是目标方位，
`normal_bearing_deg` 是将 Tag 法线定向到相机至 Tag 半球后的水平角，
`facing_error_deg` 是标签法线与视线的夹角，`reprojection_error_px` 是角点
重投影平均误差，`image_margin_px` 是 Tag 四角投影到 640×480 图像边缘的最小
距离，`transform` 是 `camera <- tag` 的完整刚体变换。对前后两次有效观测调用
`pose_motion.relative_tag_motion`，会先求相机原点在 Tag 坐标中的变化，再转换到
动作前相机坐标，得到米制 `forward/lateral/vertical` 位移和 `yaw_deg`。这些是
相对于静止 Tag 的相对运动，不是带世界原点的全局绝对位移，也不是编码器真值。
目标停止距离为相机光心到 Tag 中心 0.50 m。将同一张 10 cm 实物标签分别放在几个
已测量的静止位置，采集多张图像，核对距离和朝向的偏差及波动。

## 已知缺陷

TonyPi SDK 的 `ActionGroupControl.runActionGroup()` 会在内部捕获底层异常并打印，然后返回。endpoint 因此无法可靠区分动作组真正成功和 SDK 已吞掉的硬件执行错误。

当前版本只能可靠报告 SDK 初始化失败、payload 或 Tag 校验失败、deadline、取消、busy 和动作组文件缺失；底层执行错误只能记录日志。修复该缺陷需要修改 SDK 或绕过 SDK 重写动作组执行逻辑，当前不做这两种高风险改动。

TonyPi 的 `runActionGroup()` 对 `go_forward` / `back` 有特殊起止逻辑；当前
导航使用普通的 `go_forward_one_step` 和 `back_one_step`，以及有限
横移、小步转体动作，均以 `times=1` 执行。取消或 deadline 时动作线程请求
`stopActionGroup()` 并等待结束；SDK 的普通动作组不能在帧组中途安全中断。
SDK 可能吞掉底层执行异常，因此动作线程正常退出只代表 SDK 调用完成，不能
单凭它推断机器人实际位移；下一次决策只看动作后的新画面。
