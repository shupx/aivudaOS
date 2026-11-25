# 机载相机、AprilTag 与 C20D 联调

在应用参数中心配置各 App，保存并重启对应服务。相机和 AprilTag 运行在配套的 ARM64 Isaac ROS 容器中。两者及机载 Zenoh Bridge 需要相同的 ROS domain。C20D 驱动可在独立 Linux ROS 2 主机上运行。

| App | 输入与配置 | 可检查的输出 |
| --- | --- | --- |
| IMX219 Isaac ROS Camera | `camera.exposure_us`、`stream.mode` 及编码参数 | `/camera/image_raw`、`/camera/camera_info`。原生图传使用 `/camera/video/h264`，官方编码器使用 `/camera/image_compressed` |
| AprilTag ROS Detector | `apriltag.tags` 中每个 ID 的实际边长，单位米；`apriltag.filter_mode` 控制是否过滤未配置 ID | `/camera/camera_info_rect`、`/tag_detections`、`/tf` |
| Gimbal Control C20D | `serial.port`，机载模板使用 `/dev/ttyTHS1`，普通 USB 串口可使用 `/dev/serial/by-id/…` | 默认发布 `state` 和 `diagnostics`，订阅三种 `command/*`，提供 `device_command` 服务，均位于 `/c20d_driver` |
| Zenoh Bridge | 两端 `vision_debug` 预设；已有自定义规则的节点只合并需要的视频规则 | 地面站的 `/<robot>/camera/video/h264`，消息类型为 `foxglove_msgs/msg/CompressedVideo` |

## 地面站看图

1. 在相机的参数中心选择 `native_nvenc` 并重启相机。使用 `off` 可以仅运行相机主干。使用 `isaac_ros_h264` 需要镜像带有 NVIDIA 官方编码器。
2. 机载 Bridge 为两条图传话题启用按需出站，地面 Bridge 为需要的话题启用按需入站。视频路由两端都设置 `max_freq: 0`；机载端设置 `max_kbps: 0`、`best_effort`、`data_low` 和 `drop`。在相机参数中控制帧率和码率。
3. 在两端 Bridge 的 ROS 环境中安装消息类型支持。Foxglove 通过地面站的 Foxglove Bridge 连接本机 ROS 图，在 Image 面板中选择 `/<robot>/camera/video/h264`。关闭最后一个订阅者后，原生编码器在空闲宽限期结束时释放。

## 只读设备验收

先加载目标 App 使用的 ROS 环境。地面站的下列命令会订阅视频并触发原生编码器，按 Ctrl+C 结束。

```sh
ros2 topic info /uav1/camera/video/h264 -v
ros2 topic hz /uav1/camera/video/h264
```

机载端可检查相机主干时间戳、AprilTag 输出和云台反馈。以下命令不会给云台发送运动命令。

```sh
ros2 topic hz /camera/camera_info
ros2 topic info /tag_detections -v
ros2 topic list | grep '^/c20d_driver/'
ros2 service type /c20d_driver/device_command
ros2 topic echo --once --field relative_angle_rpy /c20d_driver/state
```

升级前记录当前活动版本、启动状态和参数。Zenoh 的路由位于每版本的运行目录，升级时需带入已有路由及会话设置。卸载旧版本会一并删除其运行目录。商店下架保留历史记录，可重新发布。

## 2026-11-22 发布验收

| 应用 | 已验证版本 |
| --- | --- |
| IMX219 Isaac ROS Camera | `2.0.0` |
| AprilTag ROS Detector | `isaacros5-imx219-1.2.0` |
| Gimbal Control C20D | `ros2-3.0.0` |
| Zenoh Bridge | `2.4.0` |

在 Orin NX 上，IMX219 和 AprilTag 同跑时测得 30.01 Hz，150 对校正相机消息和检测数组时间戳一致。标定合成图分别验证了小标签 0 和大标签 77 的位姿。原生和 Isaac ROS 官方两条 H.264 路线均通过独立解码。原生路线从机载 ROS 经 Zenoh、地面 Foxglove Bridge 到 Chrome WebCodecs，全程解码 60/60 帧，960 × 540，14.88 Hz。关闭地面订阅后，机载 ROS 图确认视频的订阅数由 1 回到 0。浏览器使用默认解码策略。

C20D 在真实串口上读到了姿态反馈，并核对了默认五个业务话题和 `device_command` 服务。控制命令、零速保持与低头顺序在伪串口上验证。驱动分别在 x86_64 Humble、x86_64 Lyrical 和机载 ARM64 Jazzy 上通过测试。
