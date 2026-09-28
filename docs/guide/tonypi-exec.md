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

endpoint 只接受 `go_to_tag`，`target_tags` 是按顺序到达的 AprilTag ID，不再把
Tag ID 映射为固定动作。每个目标都按“云台置正前方 → 获取新鲜图像 → 启动一个
连续动作段 → 高频观测并在条件满足时停止 → 重新规划”的循环处理；目标稳定满足
停止条件后才发布该目标的路线进度。

导航期间云台必须保持相机光轴与机身正前方对齐。每次机身动作前，endpoint 都会
将 PWM 舵机 1/2 置于 `1500/1435`，等待约 0.2 秒稳定，再重新观测后执行动作。
这两个值已在真机上确认对应期望的正前方姿态。

接近阶段暂不使用 `facing_error` 作为硬阈值，只要求 bearing 居中且 Tag 四角投影
距离图像边缘至少 20 px；这样可以先安全接近而不因单纯平面倾角频繁横移。进入
`0.50 ± 0.08 m` 距离范围后，终端阶段才同时要求 bearing 绝对值不超过 `5°`、
标签相对朝向误差不超过 `10°`，并连续满足 3 帧。目标初始不可见直接失败；机身
动作后短暂丢失目标时最多等待 1 秒。若终端阶段连续 3 帧没有可用的有符号侧移方向，
当前版本报告不可收敛。没有上层 deadline 时，endpoint 为整条路线使用 120 秒默认期限。

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

TonyPi 的 `runActionGroup()` 还包含前进/后退动作的特殊起始和结束逻辑。当前导航
在后台线程以 `times=0` 运行 `go_forward_one_small_step`、`back`、`left_move`、
`right_move` 或小步转向动作；视觉线程持续读取新帧，在到达、需要重规划、目标丢失、取消或
deadline 时调用 `stopActionGroup()`。对于 `go_forward`/`back`，SDK 会在停止时
执行对应的 `*_end` 动作；当前使用的 `go_forward_one_small_step` 是普通有限动作组，
会在当前动作帧组结束后退出，不执行 `go_forward_end`。SDK 会吞掉底层动作异常，因此连续动作线程的结束和后续
视觉观测都必须成功，不能仅凭 SDK 函数返回推断硬件成功。
