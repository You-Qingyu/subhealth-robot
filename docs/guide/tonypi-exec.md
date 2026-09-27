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

## 第一版动作映射

```text
Tag 1 → turn_left
Tag 2 → go_forward_one_step
Tag 3 → turn_right
```

第一版只支持 `go_to_tag`，不读取摄像头；`target_tags` 按顺序逐个执行。

## 已知缺陷

TonyPi SDK 的 `ActionGroupControl.runActionGroup()` 会在内部捕获底层异常并打印，然后返回。endpoint 因此无法可靠区分动作组真正成功和 SDK 已吞掉的硬件执行错误。

当前版本只能可靠报告 SDK 初始化失败、payload 或 Tag 校验失败、deadline、取消、busy 和动作组文件缺失；底层执行错误只能记录日志。修复该缺陷需要修改 SDK 或绕过 SDK 重写动作组执行逻辑，当前不做这两种高风险改动。

TonyPi 的 `runActionGroup()` 还包含前进/后退动作的特殊起始和结束逻辑，动作组调用次数及实际步幅由 SDK 和 `.d6a` 文件共同决定。endpoint 不自行重写这套逻辑，因此第一版的“执行一次动作组”不等价于可精确控制一个物理步长；后续视觉导航阶段需要重新验证动作组语义。
