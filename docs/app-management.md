# AivudaOS App 管理

## 概述

AivudaOS 通过 **本地上传安装包** 的方式管理应用。每个 App 以 `.tar.gz` 或 `.zip` 压缩包上传，包内必须包含 `manifest.yaml` 描述文件。系统支持多版本共存、版本切换、进程生命周期管理和自启动。

当前 UI 还支持“在线应用商店”入口：从 aivudaAppStore 的 `store` API 查看应用与版本，先下载安装包到浏览器本机，再一键上传到 AivudaOS 安装。

前端 UI 支持 `zh-CN / en-US` 语言切换（Dashboard 左侧栏入口），并将选择持久化到本地存储。当前版本只对前端固定文案做国际化，后端返回的动态文本（如 SSE 日志、错误详情）按原文显示。

## 核心模块

| 模块 | 路径 | 职责 |
|---|---|---|
| InstallerService | `core/apps/installer.py` | 解压安装包、解析 manifest、写入文件和数据库 |
| VersioningService | `core/apps/versioning.py` | 多版本目录管理、symlink 切换 |
| RuntimeService | `core/apps/runtime.py` | 启动/停止/重启、autostart、卸载 |
| SystemdRuntimeBackend | `core/apps/systemd_runtime.py` | systemd 单元生成与 systemctl 调用 |
| ConfigService | `core/config/service.py` | 每个 App 的 YAML 配置读写 |

依赖注入在 `gateway/deps.py`，API 路由在 `gateway/routes/apps.py`。

## 安装包格式

```
my-app-1.0.0.tar.gz
├── manifest.yaml        # 必须
├── start.sh             # 入口脚本
├── assets/
│   └── icon.png         # 可选，应用图标
└── ...                  # 其他应用文件
```

> 支持包内有一层包裹目录（如 `my-app/manifest.yaml`），系统会自动向下查找。
> 安装时会校验 `run.entrypoint` 是否存在，并自动补齐可执行权限（`chmod +x`）。
> App 图标由 manifest 的 `icon` 字段指定（可选）；未指定或文件不存在时使用默认图标。

### manifest.yaml 字段

```yaml
app_id: my-app                 # 唯一标识（必填）
name: My App                   # 显示名称
version: 1.0.0                 # 版本号（必填）
description: 一个示例应用
run:
  entrypoint: ./start.sh       # 启动入口（必填）
  args: []                     # 启动参数
icon: ./assets/icon.png        # 应用图标路径（可选，相对安装根目录）
pre_install: ./scripts/pre_install.sh      # 安装前脚本（可选）
pre_uninstall: ./scripts/pre_uninstall.sh  # 卸载前脚本（可选）
update_this_version: ./scripts/update_this_version.sh # update_this_version 脚本（可选）
default_config: {}             # 默认配置，安装时写入 config/apps/{app_id}.yaml
config_schema: null            # 配置校验 schema（可选）
```

### 可选生命周期脚本

- `pre_install`：安装时执行（严格模式，非 0 返回码会中断安装）
- `pre_uninstall`：卸载时执行（严格模式，非 0 返回码会中断卸载）
- `update_this_version`：通过 API 手动触发的版本更新脚本（严格模式）


脚本执行规则：

- 脚本字段为安装包内相对路径
- pre_install 在最终版本目录中执行（不是上传临时目录）
- 执行前会自动补齐可执行权限（`chmod +x`）
- 不设置超时，允许用户手动终止
- 输出写入 `data/logs/os/install.log`
- 同时通过操作事件流实时回传到前端
- `pre_install` 支持 PTY 交互模式（可接收 sudo 密码、`y/n` 等输入）

覆盖安装（同版本 `overwrite=true`）时，会先重建该版本目录，再执行 pre_install。


## 文件系统布局

```
aivudaOS/
├── apps/                          # 所有 App 安装目录
│   └── {app_id}/
│       ├── versions/
│       │   ├── 1.0.0/            # 版本目录（实际文件）
│       │   └── 1.1.0/
│       └── active -> versions/1.1.0   # symlink 指向当前激活版本
├── config/
│   └── apps/
│       └── {app_id}.yaml         # 每个 App 的运行配置
├── data/
│   ├── aivuda.db                 # SQLite 数据库
│   └── uploads/                  # 上传临时目录
```

## 数据库表

### app_installation

| 列 | 类型 | 说明 |
|---|---|---|
| app_id | TEXT | App 唯一标识（联合主键） |
| version | TEXT | 版本号（联合主键） |
| install_path | TEXT | 版本目录绝对路径 |
| status | TEXT | 安装状态（`installed`） |
| installed_at | INTEGER | 安装时间戳 |
| manifest | TEXT | manifest JSON 全文 |

### app_runtime

| 列 | 类型 | 说明 |
|---|---|---|
| app_id | TEXT | 主键 |
| running | INTEGER | 是否正在运行（0/1） |
| autostart | INTEGER | 是否自启动（0/1） |
| pid | INTEGER | 进程 PID |
| last_started_at | INTEGER | 上次启动时间戳 |
| last_stopped_at | INTEGER | 上次停止时间戳 |

## 安装流程

```
上传 .tar.gz / .zip
       │
       ▼
  解压到临时目录
       │
       ▼
  查找 manifest.yaml（根目录或一级子目录）
       │
       ▼
  解析 → AppManifest 对象
       │
       ▼
  创建版本目录 apps/{app_id}/versions/{version}/
       │
       ▼
  复制所有文件到版本目录
       │
       ▼
  写入 app_installation 表 + app_runtime 表
       │
       ▼
  初始化 config/apps/{app_id}.yaml
       │
       ▼
  创建 symlink: apps/{app_id}/active → versions/{version}
```

## 运行时管理

运行时支持两种模式，由 `config/os.yaml` 决定：

- `runtime_process_manager`: `auto` | `systemd` | `popen`
- `runtime_systemd_scope`: `user` | `system`

### systemd 模式（优先）

- 启动/停止/重启通过 `systemctl` 调用对应 `.service`
- 自启动对应 `systemctl enable/disable`
- 状态由 `systemctl show` 查询并同步到 `app_runtime`
- 单元名格式：`aivuda-app-{app_id}.service`（会做安全规范化）

### popen 回退模式

- **启动**：根据 `manifest.run.entrypoint` 构建命令，`subprocess.Popen` 启动（`start_new_session=True`）
- 运行时会统一注入日志实时输出环境（例如 `PYTHONUNBUFFERED=1`、`ROSCONSOLE_STDOUT_LINE_BUFFERED=1`），并在可用时自动使用 `stdbuf -oL -eL` 包装启动命令，减少日志缓冲延迟
- **停止**：`os.kill(pid, SIGTERM)`
- PID 记录在 `app_runtime` 表
- 进程自然退出时会自动回写 `app_runtime`：`running=0`、`pid=NULL`、更新 `last_stopped_at`

### 自启动（Autostart）

通过 `POST /aivuda_os/api/apps/{app_id}/autostart` 设置：

- systemd 模式：更新 unit 的 enabled 状态，同时同步 `app_runtime.autostart`
- popen 模式：仅更新 `app_runtime.autostart`，由后端启动时回放拉起

后端启动阶段：

- systemd 模式：跳过 DB 自启动回放（由 systemd 自身管理）
- popen 模式：扫描 `autostart=1` 并执行 `start()`

## API 端点

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/aivuda_os/api/apps/upload` | 上传安装包（首次安装） |
| POST | `/aivuda_os/api/apps/{app_id}/upgrade` | 上传新版本（升级，若正在运行则自动重启） |
| POST | `/aivuda_os/api/apps/{app_id}/update_this_version` | 执行指定已安装版本的 `update_this_version` 脚本 |
| GET | `/aivuda_os/api/apps/operations/{operation_id}` | 查询操作状态 |
| GET | `/aivuda_os/api/apps/operations/{operation_id}/events` | SSE 实时事件流 |
| POST | `/aivuda_os/api/apps/operations/{operation_id}/cancel` | 取消运行中的操作 |
| WS | `/aivuda_os/api/apps/operations/{operation_id}/interactive/ws?token=...` | 交互输入通道（写入脚本 stdin） |
| GET | `/aivuda_os/api/apps/installed` | 已安装应用列表 |
| GET | `/aivuda_os/api/apps/{app_id}/status` | 应用详情（安装信息 + 运行状态） |
| POST | `/aivuda_os/api/apps/{app_id}/start` | 启动 |
| POST | `/aivuda_os/api/apps/{app_id}/stop` | 停止 |
| POST | `/aivuda_os/api/apps/{app_id}/restart` | 重启 |
| POST | `/aivuda_os/api/apps/{app_id}/autostart` | 设置自启动 `{ "enabled": true }` |
| GET | `/aivuda_os/api/apps/{app_id}/versions` | 版本列表 |
| POST | `/aivuda_os/api/apps/{app_id}/switch-version` | 切换版本 `{ "version": "1.0.0", "restart": true }` |
| POST | `/aivuda_os/api/apps/{app_id}/uninstall` | 卸载 `{ "purge": false, "version": null }` |
| GET | `/aivuda_os/api/apps/{app_id}/config` | 获取 App 配置 |
| PUT | `/aivuda_os/api/apps/{app_id}/config` | 更新 App 配置 `{ "version": 1, "data": {...} }` |

> 所有端点需要 `token` 参数进行身份验证。

## 在线应用商店流程

1. 在 UI 的“在线应用商店”页面设置 `appstore_base_url`（保存到 `config/os.yaml`）。
2. 前端调用：`{appstore_base_url}/aivuda_app_store/store/index` 获取应用卡片列表。
3. 点击应用后调用：`.../store/apps/{app_id}` 查看版本详情。
4. 点击“下载到本机”后，前端调用 `.../download-url` 与 `.../download`，将安装包下载到浏览器本机。
5. 点击“安装到 AivudaOS”后，前端把该下载文件通过 `POST /aivuda_os/api/apps/upload` 上传给本机 AivudaOS，安装流程与手动上传一致。

当前在线商店页已改为单按钮“下载并安装到 AivudaOS”流程：

1. 先触发浏览器原生下载，保存到用户指定的本机位置（由浏览器下载设置决定）。
2. 随后询问是否立即安装。
3. 若确认，打开与“手动上传新应用安装包”完全复用的上传安装弹窗。
4. 用户在弹窗中选择刚下载的本机文件并提交安装，后端仍走 `POST /aivuda_os/api/apps/upload` 同一流程。

### 实时操作事件（SSE）

`POST /aivuda_os/api/apps/upload`、`POST /aivuda_os/api/apps/{app_id}/uninstall`、`POST /aivuda_os/api/apps/{app_id}/update_this_version` 现在返回：

```json
{
     "ok": true,
     "operation_id": "...",
     "status": "queued"
}
```

前端随后连接：

`GET /aivuda_os/api/apps/operations/{operation_id}/events?token=...`

典型事件：

- `status`：阶段状态（prepare/extract/pre_install/remove/completed 等）
- `log`：脚本输出逐行内容（stdout/stderr）
- `error`：失败信息
- `completed`：操作结束（成功或失败）

### 交互安装输入（WS）

`POST /aivuda_os/api/apps/upload` 的响应包含：

- `interactive_enabled`: 是否支持交互
- `interactive_ws_path`: WebSocket 路径

前端建议并行建立两条链路：

1. SSE 接收状态与日志输出（只读）
2. WS 发送交互输入（可写）

输入协议：

- 客户端可发送纯文本，或 JSON `{ "type": "input", "data": "..." }`
- 后端会自动补 `\n` 后写入脚本 stdin
- 任务结束后交互会话自动关闭

取消操作：

- 前端可调用 `POST /operations/{operation_id}/cancel` 请求取消
- 服务端会将状态置为 `cancelling`，并在脚本退出后结束为 `canceled`

## 版本管理

- 同一 App 可安装多个版本，共存于 `apps/{app_id}/versions/` 下
- `active` symlink 指向当前激活版本
- `switch-version` 可切换激活版本，可选自动重启
- `uninstall` 可删除单个版本或整个 App（`purge=true` 同时删除配置）

## 升级流程

`POST /aivuda_os/api/apps/{app_id}/upgrade` 上传新版本包：

1. 安装新版本（同 install 流程）
2. 自动激活新版本
3. 若 App 原先正在运行，自动重启

## update_this_version 脚本执行

`POST /aivuda_os/api/apps/{app_id}/update_this_version`

请求体：

```json
{
     "version": "1.2.3"
}
```

行为：

1. 校验 `version` 已安装
2. 读取该版本 manifest 的 `update_version` 字段（逻辑名称：`update_this_version`）
3. 若有脚本则执行；若无脚本则返回 `skipped=true`
4. 运行过程通过 SSE 事件流实时返回脚本输出
