# AivudaOS开发

aivudaOS：部署于机器人机载电脑上的轻量操作系统，用于从 aivudaAppStore 安装和运行应用。

## 目录结构

- `aivudaos/core/`: 核心业务逻辑（纯 Python，不依赖 HTTP）
- `aivudaos/gateway/`: FastAPI 服务层，提供core service的统一的REST 接口，作为后端http server
- `aivudaos/resources/ui/`: 操作界面源码（Vue 3 + Vite）
- `aivudaos/resources/`: 打包后的运行时资源根目录
- `aivudaos/resources/scripts/`: 开发态/运维态入口脚本

## Python 兼容性约束

- 后端 Python 代码必须兼容 `Python 3.8`。
- 类型标注不要使用 `dict[str, Any]`、`list[str]`、`set[str]`、`tuple[int, int]` 这类 3.9+ 内建泛型写法。
- 统一使用 `typing.Dict`、`typing.List`、`typing.Set`、`typing.Tuple`，避免在 Pydantic 等运行时解析注解时触发兼容性问题。

其中常用运行时资源位置：

- `aivudaos/resources/caddy/Caddyfile_template`
- `aivudaos/resources/shell_helpers/`
- `aivudaos/resources/ui/dist/`

## 运行时工作目录（默认）

运行时目录默认放在：

- `$HOME/aivudaOS_ws/apps` （app安装目录）
- `$HOME/aivudaOS_ws/config`（app和系统的参数配置文件会粘到这个文件夹，读写参数都在这）
- `$HOME/aivudaOS_ws/data`（log、runtime缓存、系统数据库等）

其中：

- `os.yaml`：系统运行参数（例如 runtime 模式），不参与磁吸。
- `sys.yaml`：公用业务参数（允许增删改），参与磁吸；默认包含 `role.id=1`。active app 的 schema 中若声明 `sys.*` 参数，后端会在磁吸重算时自动补齐到这里，且不会因 app 切换或卸载自动删除。

`os.yaml` 默认还会生成 `avahi_hostname`（格式 `robot-xxx`，3 位十六进制，小写），并用于 `.local` 访问域名。

可通过环境变量覆盖：

```bash
export AIVUDAOS_WS_ROOT=/your/custom/path
```

首次启动会自动创建所需目录和默认配置文件（`os.yaml`、`sys.yaml`、`users.yaml`、`magnets.yaml`）。

## 访问入口

caddy代理的入口： [http://127.0.0.1:80]()（仅本机） 或者 [https://<avahi_hostname>.local:443]() （远端）

`<avahi_hostname>`可由以下命令查看：

```bash
# 用下方的命令查看avahi用的hostname，优先看/etc/avahi/avahi-daemon.conf里的host-name=，如果没有设置就是本机hostname
HOST=$(grep -E '^host-name=' /etc/avahi/avahi-daemon.conf | cut -d= -f2); [ -n "$HOST" ] && echo ${HOST} || hostname
```

比如上方指令如果输出`robot-2b5`，那么远端可以访问 [https://robot-2b5.local:443](https://robot-2b5.local:443)

## 启动方法

### 开发模式（热重载，单命令）

`aivudaos/resources/scripts/_run_aivudaos_stack.sh --dev` 会同时启动：

- 后端：`python3 -m uvicorn aivudaos.gateway.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir aivudaos/gateway --reload-dir aivudaos/core`
- 前端：`cd aivudaos/resources/ui && npm exec vite build -- --watch`
- 代理：`cd ~ && ./aivudaOS_ws/.tools/caddy/caddy run --config ${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile`

```bash
cd aivudaOS/
# 先安装python依赖和下载caddy（做一次就行）
pip install -r requirements.txt
aivudaos/resources/scripts/_download_caddy.sh
# 再启动开发模式脚本
aivudaos/resources/scripts/_run_aivudaos_stack.sh --dev
```

说明：`--dev` 模式下会持续监听后端与前端变更并自动重载；按 `Ctrl+C` 会统一停止后端、前端 watch 和 caddy。
开发模式脚本会自动把源码仓库根加入 `PYTHONPATH`，因此即使当前环境还没执行 `pip install --user -e .`，也可以直接启动后端。
如果当前 shell 已激活 `conda` 环境，脚本会优先使用该环境的 `python`。

### 生产模式（gunicorn + uvicorn worker）

#### 手动启动：

gateway 启动后自动检测 `aivudaos/resources/ui/dist/`，将前端静态文件与 API 挂载在同一端口。

打包规则：

- wheel 仅包含 `aivudaos/resources/ui/dist/`
- sdist 不包含 `aivudaos/resources/ui/dist/` 和 `node_modules/`，只保留前端源码，便于重新构建

```bash
# 构建前端静态文件
cd aivudaos/resources/ui && npm install && npm run build && cd ../../..

# 启动（推荐，后端 gunicorn + caddy）
aivudaos/resources/scripts/_run_aivudaos_stack.sh

# 或仅启动后端（gunicorn + uvicorn worker）注意：保持 `-w 1`。安装任务状态存于进程内存，多 worker 会导致任务查询 404。
python3 -m gunicorn -w 1 -k uvicorn.workers.UvicornWorker aivudaos.gateway.main:app -b 127.0.0.1:8000
```

#### 开机自启动：

安装开机自启动servcie：

```bash
aivudaos/resources/scripts/install_aivudaos.sh
```

`aivudaos/resources/scripts/install_aivudaos.sh` 会将解析到的 `avahi_hostname` 同步写入：

- `/etc/avahi/avahi-daemon.conf` 的 `[server]` 块 `host-name=<value>`
- `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile` 的 HTTPS 站点 `https://<value>.local:443`

并在 hostname 发生变化时执行 caddy reload。

如果执行安装脚本时已经激活 `conda` 环境，生成的 `aivudaos.service` 会固定使用该环境对应的 Python 解释器。

卸载自启动：

```bash
aivudaos/resources/scripts/uninstall_aivudaos.sh
```

## Caddy 配置说明

Caddy 托管前端静态文件并反代 `/aivuda_os/api`，其中 HTTP 仅监听 `127.0.0.1:80`，并通过 `tls internal` 提供 HTTPS 443，详见 [`docs/deploy-caddy.md`](docs/deploy-caddy.md)。

另外，App 内置 UI（`/{app_id}/ui/`）也由 Caddy 直接托管：

- 后端会根据各 app active 版本的 `manifest.ui_index_path` 自动生成 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/caddy/{app_id}.ui.caddy`
- 在安装、卸载、切换版本时会自动重写顶层 Caddyfile 的 import 区块并 reload Caddy
- 如 manifest 额外声明 `ui_mount_type: qiankun`，AivudaOS 会将其视为可被 PanelHub 自动发现的 qiankun 子应用入口

## App 运行模式（systemd / popen）

应用生命周期支持两种后端：

- `systemd`：由 `.service` 管理 `start/stop/restart/autostart`
- `popen`：使用 Python `subprocess.Popen`（兼容回退）

通过 `$HOME/aivudaOS_ws/config/os.yaml`（或 `$AIVUDAOS_WS_ROOT/config/os.yaml`）的 OS 配置项控制：

- `runtime_process_manager`: `auto` | `systemd` | `popen`（默认 `auto`）
- `runtime_systemd_scope`: `user` | `system`（默认 `user`）
- `avahi_hostname`: Avahi mDNS 主机名（默认自动生成 `robot-xxx`）

说明：

- `auto`：检测到可用 systemd 时优先使用 systemd，否则自动回退到 `popen`
- `systemd`：优先尝试 systemd；若当前环境不可用会回退到 `popen`
- `popen`：始终使用旧进程模型

日志接口保持不变：`GET /aivuda_os/api/apps/{app_id}/logs` 继续读取 `$HOME/aivudaOS_ws/data/logs/apps/{app_id}/current.log`（或 `$AIVUDAOS_WS_ROOT/data/...`）。

App 启动时会注入配置路径相关环境变量：

- `AIVUDA_APP_CONFIG_PATH`：当前 app 当前版本配置文件路径
- `AIVUDA_APP_ID` / `AIVUDA_APP_VERSION`
- `AIVUDA_APP_HELPERS_ENTRY_PATH`：统一 helper 入口（`aivudaos/resources/shell_helpers/aivuda_app_helpers.sh`）

推荐在 app `start.sh` 先 `source "$AIVUDA_APP_HELPERS_ENTRY_PATH"`，再用 `aivuda_yaml_get` 按 dotted path 读取配置。

## 默认账号

- 用户名: `admin`
- 密码: `admin123`

## 参数弹窗复制

参数中心的默认值弹窗及数组/对象编辑弹窗共用 `src/services/core/clipboard.js`：优先使用 Clipboard API，在 API 缺失（非安全 HTTP）或被 Electron WebView 权限拒绝时，降级为文本选区复制；失败显示国际化提示。默认值弹窗逻辑位于 `src/composables/useDefaultValueModal.js`。

## 前端多语言

- UI 支持语言切换：`简体中文 (zh-CN)` / `English (en-US)`。
- 切换入口位于 Dashboard 左侧栏底部的 `语言` 下拉框。
- 语言偏好会持久化到浏览器本地存储（key: `aivuda_ui_locale`）。
- 首版仅翻译前端固定文案；后端实时消息/API 错误详情保持原文透传显示。

## 前端路由

| 路径 | 功能 |
|------|------|
| `/login` | 登录 |
| `/dashboard/status` | 会话状态 |
| `/dashboard/apps` | 应用安装 / 版本管理 |
| `/dashboard/apps/configs` | 统一应用参数配置（所有 app active 版本） |
| `/dashboard/apps/:appId/config` | 应用参数配置（按版本） |
| `/dashboard/store` | 在线应用商店（查看与下载/安装） |
| `/dashboard/settings` | 系统设置（AivudaOS 服务 stop/restart/uninstall/autostart、sudo 免密、重登录、APT 源配置） |

## API 接口

### 认证
- `POST /aivuda_os/api/auth/login`
- `GET  /aivuda_os/api/auth/me`

### 配置
- `GET  /aivuda_os/api/config`（`sys.yaml`）
- `PUT  /aivuda_os/api/config`（`sys.yaml`）
- `GET  /aivuda_os/api/config/os`（`os.yaml`）
- `PUT  /aivuda_os/api/config/os`（`os.yaml`）
- `GET  /aivuda_os/api/config/system/sudo-nopasswd`（读取 sudo 免密状态）
- `PUT  /aivuda_os/api/config/system/sudo-nopasswd`（更新 sudo 免密状态）
- `POST /aivuda_os/api/config/system/relogin`（注销并重启 `user@UID.service`，用于用户组变更后重登录）
- `POST /aivuda_os/api/config/system/avahi/restart`（重启 `avahi-daemon.service`）
- `GET  /aivuda_os/api/config/system/aivudaos-service`（读取 AivudaOS 自身 systemd user service 状态）
- `POST /aivuda_os/api/config/system/aivudaos-service/autostart`（启用/禁用 AivudaOS 自身自启动）
- `POST /aivuda_os/api/config/system/aivudaos-service/{action}`（触发 `stop` / `restart` / `uninstall`，以后端脱离当前进程组的方式后台执行）
- `GET  /aivuda_os/api/config/system/apt-sources-list`（自动检测 Ubuntu 主源文件，返回路径和格式）
- `GET  /aivuda_os/api/config/system/apt-sources-list/backups`（读取 APT 源备份列表）
- `PUT  /aivuda_os/api/config/system/apt-sources-list`（写入 APT 源，写入前自动创建时间戳备份，并自动执行 `apt update`）
- `POST /aivuda_os/api/config/system/apt-sources-list/restore`（按备份版本恢复 APT 源，并自动执行 `apt update`）

说明：standalone 模式下，当 `avahi_hostname` 通过 OS 参数更新后，后端会立即同步修改运行时 `Caddyfile` 的 HTTPS 域名为 `https://<avahi_hostname>.local:443`，若 Caddy 正在运行会尝试自动 reload。设置 `AIVUDAOS_EMBEDDED_MODE=1` 后，hostname 仍会写入 `os.yaml`，但不会写入/重启 Avahi，也不会同步或 reload HTTPS hostname 站点；App UI 和自定义路由仍会照常生成并 reload。

### 嵌入式模式

桌面管理器托管 AivudaOS 时，可设置：

```bash
export AIVUDAOS_EMBEDDED_MODE=1
export AIVUDAOS_WS_ROOT=/path/to/private/aivudaos-workspace
```

嵌入式模式默认使用 `aceswarm` 作为 `avahi_hostname`，不会依赖本机 Avahi 或修改 HTTPS hostname。管理器应在 `AIVUDAOS_WS_ROOT/config/Caddyfile` 中提供自己的 loopback Caddy 站点；应用安装、卸载和版本切换仍由 AivudaOS 生成应用路由并 reload Caddy。

### APT 源配置说明

- UI 入口：`系统设置 -> 配置 APT 源`。
- 自动按实际文件布局检测主源：存在 `/etc/apt/sources.list.d/ubuntu.sources` 时使用它（Ubuntu 24.04 起默认的 deb822 格式），否则使用 `/etc/apt/sources.list`（传统 deb/deb-src 格式）。不依赖版本号，因此兼容升级安装和自定义镜像；其他第三方源不会被修改。
- 每次写入或恢复前都会自动备份到 `/var/backups/aivudaos/apt-sources/`，按目标文件分别命名为 `sources.list.<timestamp>.bak` 或 `ubuntu.sources.<timestamp>.bak`。备份列表仅显示当前目标的备份，跨目标恢复会被拒绝；旧 sources.list 备份 ID 保持兼容。
- 写入和恢复后会自动执行 `apt update`，输出会在前端弹窗里显示。
- 前端会收集 sudo 密码并仅用于当前请求，不会持久化到浏览器存储。

## 内置 MCP

MCP 在 FastAPI 主进程中提供 `/aivuda_os/mcp`，随 AivudaOS 服务一起启动。
本机为 `http://127.0.0.1/aivuda_os/mcp`，远端为
`https://<avahi_hostname>.local/aivuda_os/mcp`，HTTP/HTTPS 均复用现有 Caddy
入口。ACEswarm 使用 `http://127.0.0.1:28790/aivuda_os/mcp`（端口可配置）。
无需 `aivudaos-mcp` 命令、独立 MCP 端口或额外代理；旧客户端地址需要更新。

根据业务 API 路由生成 46 个 HTTP 工具及 1 个交互 WebSocket 工具，保留原有
5 个工具名。MCP 和静态 UI 不参与工具生成。内部传输通过 ASGI 调用同一应用
的 API，保留认证、参数校验、middleware、异步任务、文件、SSE 和 WebSocket。
同步 MCP 调度在工作线程中执行，API 请求在服务事件循环中运行，不回连 Caddy。

agent 无 token 时先使用默认 `admin / admin123` 自动登录，主进程缓存临时
自动 token，并发请求共用登录，失效后重新登录并重试一次。仅默认/配置登录
被拒绝时才提示用户提供当前账号密码，再调用 `login` 并显式传入返回的 token。
网络故障不触发索要凭据；手动登录或 Bearer 身份不会覆盖自动账号，显式 token
被拒绝时也不会自动切换默认账号。支持 `AIVUDAOS_MCP_USERNAME` / `PASSWORD` 和
显式 `AIVUDAOS_MCP_TOKEN`，`AIVUDAOS_MCP_MAX_BYTES` 默认 64 MiB；其余旧独立
服务的绑定地址、端口和入站访问 token 配置不再生效。
旧标准 Caddy matcher 会在 standalone 启动时迁移，保留自定义端口和应用导入；
自定义 matcher 需加入 `/aivuda_os/mcp`。详细使用和测试见
[docs/mcp.md](docs/mcp.md)。

### 应用管理
- `POST /aivuda_os/api/apps/repo/sync` — 从仓库同步应用目录
- `GET  /aivuda_os/api/apps/catalog` — 可安装应用列表
- `GET  /aivuda_os/api/apps/installed` — 已安装应用列表
- `POST /aivuda_os/api/apps/{app_id}/install` — 安装应用
- `GET  /aivuda_os/api/apps/tasks/{task_id}` — 查询安装任务进度
- `GET  /aivuda_os/api/apps/{app_id}/status` — 应用运行状态
- `POST /aivuda_os/api/apps/{app_id}/start` — 启动
- `POST /aivuda_os/api/apps/{app_id}/stop` — 停止
- `POST /aivuda_os/api/apps/{app_id}/autostart` — 设置开机自启
- `GET  /aivuda_os/api/apps/{app_id}/versions` — 已安装版本列表
- `POST /aivuda_os/api/apps/{app_id}/switch-version` — 切换激活版本
- `POST /aivuda_os/api/apps/{app_id}/update_this_version` — 执行指定版本 update_this_version 脚本
- `POST /aivuda_os/api/apps/{app_id}/uninstall` — 卸载（支持指定版本或全部）
- `GET /aivuda_os/api/apps/operations/{operation_id}` — 查询安装/卸载/更新操作状态
- `GET /aivuda_os/api/apps/operations/{operation_id}/events` — SSE 实时操作输出流
- `POST /aivuda_os/api/apps/operations/{operation_id}/cancel` — 请求取消运行中的操作（如上传安装）
- `WS /aivuda_os/api/apps/operations/{operation_id}/interactive/ws` — 安装交互输入通道（query 带 `token`）
- `GET /aivuda_os/api/apps/{app_id}/icon` — 获取应用图标（由 manifest `icon` 字段指定，缺省回退默认图标）
- `GET /{app_id}/ui/` — 获取应用内置 UI 首页（由 Caddy 静态托管，manifest `ui_index_path` 可选）
- `GET /aivuda_os/api/apps/installed` / `GET /aivuda_os/api/apps/{app_id}/status` 会额外返回 `panelhub_mountable`，用于区分“有内置 UI”和“可被 PanelHub 挂载”
- `GET /{app_id}/ui/{asset_path}` — 获取内置 UI 静态资源（由 Caddy 静态托管）
- `GET /aivuda_os/api/apps/configs/active` — 获取所有已安装 app 的 active 配置、schema 与约束（统一参数页使用）
- `GET  /aivuda_os/api/apps/{app_id}/config` — 读取应用配置（可选 query: `app_version`）
- `PUT  /aivuda_os/api/apps/{app_id}/config` — 更新应用配置（body 可带 `app_version`）

## 安装交互输入（pre_install）

- 上传安装返回中会携带 `interactive_enabled` 与 `interactive_ws_path`。
- 脚本输出继续走 SSE：`/api/apps/operations/{operation_id}/events`。
- 需要输入时，前端通过 WebSocket 连接 `interactive_ws_path?token=...` 并发送文本输入；后端会自动追加换行写入脚本 stdin。
- 当前交互链路基于 PTY，支持 `sudo` 密码、`y/n` 等命令行提示输入。

## 在线应用商店接入

- UI 左侧菜单新增“在线应用商店”，位置在“应用菜单”下方。
- 商店地址由前端页面输入并保存在当前浏览器本地存储（localStorage，key: `aivuda_ui_appstore_base_url`）。
- 前端按“商店地址 + /aivuda_app_store/store/...”拼接调用 store API（列表、详情、下载链接、下载文件）。
- 下载流程：先下载应用包到用户浏览器本机；安装流程：再将该包按本地上传接口 `POST /aivuda_os/api/apps/upload` 传给 AivudaOS 安装。
# Embedded-mode tests

Run `python3 -m unittest discover -s tests -p 'test_embedded_mode.py'` to
verify that desktop embedding skips Avahi and HTTPS hostname coupling while
standalone hostname updates retain their existing behavior.

### Popen application shutdown ownership

The gateway shutdown hook stops only Popen applications started by that runtime
instance, concurrently, before releasing its application guardian. Systemd apps
keep their existing service lifecycle. Explicit stop waits for confirmed process
exit before recording stopped state. Linux `/proc` start times protect against
PID reuse; observed descendants include children which start new sessions.
Cleanup allows five seconds for SIGTERM, then escalates surviving processes to
SIGKILL and verifies exit. A detached Python guardian monitors a private pipe;
backend crashes/SIGKILL close that pipe and trigger the same cleanup. Application
entrypoints should still implement their own graceful signal handling.

Regression checks: `python -m unittest discover -s tests`, plus ACEswarm's
`npm run test:cleanup`, which installs a disposable Popen fixture in an isolated
workspace and verifies normal/system quit, SIGTERM and SIGKILL leave no fixture
or service processes. The fixture includes a detached child ignoring SIGTERM.

## App 额外环境变量

系统设置页面最下方提供变量名/值表格，支持增加、删除、修改并统一保存。配置保存在 `os.yaml` 的 `runtime_environment` 字符串映射中；新建配置及旧配置缺少该字段时默认加入 `ROS_LOCALHOST_ONLY: "1"`。显式保存 `{}` 可删除所有额外变量，重启不会重新填充。

通过已有 `GET/PUT /aivuda_os/api/config/os` API 读写，PUT 请求包含完整 `data` 和 GET 返回的 `version`；版本过期返回 409，避免覆盖另一用户的配置。示例 data 字段：

```yaml
runtime_environment:
  ROS_LOCALHOST_ONLY: "1"
  ROS_DOMAIN_ID: "10"
```

所有 app 的启动、重启、自启动和 systemd unit 重建均读取这份配置。额外变量覆盖继承环境和默认日志变量，内部 `AIVUDA_*` 路径变量保留。变量名必须匹配 `[A-Za-z_][A-Za-z0-9_]*`，不允许 `AIVUDA_*`；值必须为不含 NUL/换行的字符串，空字符串有效。systemd 会转义引号、反斜杠和百分号，保持变量的字面值。

保存后自动刷新 app systemd unit 并 daemon-reload；不会自动重启运行中的 app，它们在下一次启动/重启时获得新值。API 返回 `runtime_environment_refresh_errors`，若部分 unit 刷新失败，UI 会说明配置已保存并显示失败原因。Popen 删除额外变量后恢复继承 AivudaOS 进程环境；该功能不修改 AivudaOS 自身或 app 安装/卸载脚本的环境。

验证：`../.venv/bin/python -m unittest discover -s tests -v`；UI 在 `aivudaos/resources/ui` 执行 `npm run build`。

## App 参数跨版本迁移

配置目录继续按 App 和版本隔离。安装新版本及切换版本（包含降级）时，以操作前
active 版本参数为来源；覆盖安装时，以被覆盖版本参数为来源。统一通过
`ConfigService.migrate_app_config` 调用 `core/config/app_migration.py`：递归合并对象，
按来源合法值、目标已有合法值、目标默认值的顺序选择；数组整体选择，不进行猜测类型转换。
仅明确禁止的额外字段会被省略，允许的动态键继续保留。来源配置不被重写。

迁移失败的字段返回 `config_migration_warnings`（path/source/reason/action），操作仍成功。
缺少无可用值的必填字段时返回 `config_valid=false`，跳过磁吸重算和自动启动；手动启动仍执行
原有完整校验。schema/default 本身无效的安装包仍按原有包校验拒绝。
磁吸重算会把不满足新字段约束的旧共享值记为冲突，保留迁移结果。

UI 上传/覆盖安装弹窗及版本切换页展示中英文 warning，说明字段和回退方式。
安装 SSE 也输出 warning；完成结果保留同一列表，轮询回退不会丢失提示。

验证：

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_config_migration_ui.mjs
cd aivudaos/resources/ui
npm run build
```

详见 [App 管理](docs/app-management.md)。
