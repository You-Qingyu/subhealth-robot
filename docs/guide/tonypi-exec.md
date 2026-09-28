# TonyPi execution endpoint

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
Tag ID 映射为固定动作。状态机只调用 `observe_tags()` 和 `execute_action(name)`：
取得当前帧所有 Tag 位姿，选择目标并决策，执行**一次有限动作组**，等动作停稳后
重新观测。目标稳定满足停止条件后才发布该目标的路线进度。

导航期间云台必须保持相机光轴与机身正前方对齐。读取画面与机身动作前都会
将 PWM 舵机 1/2 置于 `1500/1435`，等待稳定后进行读帧或执行动作。
这两个值已在真机上确认对应期望的正前方姿态。

初始或途中丢失目标时，只执行有限的小步原地转体搜索，不能盲目前进或横移。
预设的搜索角 `theta=90°` 对应光轴左右各 45°，接近角 `alpha=60°` 对应
机身正前方左右各 30°；这两个角度不是实测相机视场。超出接近角先逐步转体，
进入接近角后以 `go_forward_one_step ×1` 接近。进入 `0.50 ± 0.08 m`
距离范围后，终端阶段先使 bearing 绝对值不超过 `5°`，再按 Tag 法线的有符号
偏差左右移动；每步停稳后重新检查距离、bearing 和 `facing_error`。三者分别
满足 `0.50 ± 0.08 m`、`≤5°`、`≤10°` 且连续三帧才算到达。无进展和
状态往返不额外报错；没有上层 deadline 时，整条路线使用 120 秒默认期限。

每一步在 `tonypi_navigation_step` 日志和 `ExecuteTask` feedback 的 `details_json`
中记录相同的结构化事件：`started` 包含目标、阶段、动作组及动作前位姿；
`observed` 包含动作后新帧位姿（目标不可见时为 `null`）、动作接口耗时及从开始
到新画面的总耗时；`stopped` 包含中断/观测错误码。阶段变化另有
`phase_changed` 事件。这里只记录观测和决策，不从 SDK 返回值推断实际位移。

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
目标停止距离为相机光心到 Tag 中心 0.50 m。将同一张 10 cm
实物标签分别放在几个已测量的静止位置，采集多张图像，核对距离和朝向的偏差及
波动。用户已通过多轮实物观测确认距离和角度测算准确；上述阈值是第一版闭环
初始值。

旧版 TonyPi 示例通过 `hiwonder.apriltag` 检测，但其依赖的动态库不一定随真机
安装；endpoint 使用 OpenCV AprilTag 字典与 `solvePnP`，并复用同一相机标定文件。

## 已知缺陷

TonyPi SDK 的 `ActionGroupControl.runActionGroup()` 会在内部捕获底层异常并打印，然后返回。endpoint 因此无法可靠区分动作组真正成功和 SDK 已吞掉的硬件执行错误。

当前版本只能可靠报告 SDK 初始化失败、payload 或 Tag 校验失败、deadline、取消、busy 和动作组文件缺失；底层执行错误只能记录日志。修复该缺陷需要修改 SDK 或绕过 SDK 重写动作组执行逻辑，当前不做这两种高风险改动。

TonyPi 的 `runActionGroup()` 对 `go_forward` / `back` 有特殊起止逻辑；当前
导航使用普通的 `go_forward_one_step` 和 `back_one_step`，以及有限
横移、小步转体动作，均以 `times=1` 执行。取消或 deadline 时动作线程请求
`stopActionGroup()` 并等待结束；SDK 的普通动作组不能在帧组中途安全中断。
SDK 可能吞掉底层执行异常，因此动作线程正常退出只代表 SDK 调用完成，不能
单凭它推断机器人实际位移；下一次决策只看动作后的新画面。
