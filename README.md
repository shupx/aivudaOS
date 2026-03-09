# AivudaOS

aivudaOS：部署于机器人机载电脑上的轻量操作系统，用于从 aivudaAppStore 安装和运行应用。

一个部署在云服务器上的示例：https://39.102.60.150:8443（手动允许证书）

## 目录结构

- `core/`: 核心业务逻辑（纯 Python，不依赖 HTTP）
- `gateway/`: FastAPI 服务层，提供core service的统一的REST 接口，作为后端http server
- `ui/`: 操作界面（Vue 3 + Vite）
- `nginx/`: Nginx 配置模板

## 运行时工作目录（默认）

运行时目录不再使用仓库内的 `apps/`、`config/`、`data/`，而是默认放在：

- `$HOME/aivudaOS_ws/apps`
- `$HOME/aivudaOS_ws/config`
- `$HOME/aivudaOS_ws/data`

其中：

- `os.yaml`：系统运行参数（例如 runtime 模式），不参与磁吸。
- `sys.yaml`：公用业务参数（允许增删改），参与磁吸；默认包含 `role.id=1`。

可通过环境变量覆盖：

```bash
export AIVUDAOS_WS_ROOT=/your/custom/path
```

首次启动会自动创建所需目录和默认配置文件（`os.yaml`、`sys.yaml`、`users.yaml`、`magnets.yaml`）。

## 快速启动

### 开发模式（热重载，两个终端）

1. 安装后端依赖

```bash
pip install -r requirements.txt
```

2. 启动 gateway（后端api gateway），这里reload是开发时用的热重载，设置只关注`apps/`和`data/`两个文件夹的变动（后端核心服务和后端REST API server），

```bash
# 实际uvicorn有bug还是关注了所有文件变化。
PYTHONPATH=. uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir gateway --reload-dir core
```

```bash
# 推荐用gunicorn
PYTHONPATH=. gunicorn gateway.main:app -k uvicorn.workers.UvicornWorker -w 1 --bind 0.0.0.0:8000 --reload
```


3. 启动前端

```bash
cd ui
npm install
npm run dev
```

打开http://localhost:5173/，`/aivuda_os/api` 自动代理到 `:8000`（vite.config.js配置了）。

### 生产模式（gunicorn + uvicorn worker）

gateway 启动后自动检测 `ui/dist/`，将前端静态文件与 API 挂载在同一端口。

```bash
# 构建前端静态文件
cd ui && npm install && npm run build && cd ..

# 启动（gunicorn 守护进程 + uvicorn worker）
PYTHONPATH=. python3 -m gunicorn -w 1 -k uvicorn.workers.UvicornWorker gateway.main:app -b 0.0.0.0:8000
```

打开 `http://<设备IP>:8000`。本地可以用http://localhost:8000

> **注意**：保持 `-w 1`。安装任务状态存于进程内存，多 worker 会导致任务查询 404。

## Nginx 生产部署（可选）

Nginx 托管前端静态文件并反代 `/aivuda_os/api`，详见 [`docs/deploy-nginx.md`](docs/deploy-nginx.md)。

## Caddy 生产部署（可选）

Caddy 托管前端静态文件并反代 `/aivuda_os/api`，支持 HTTP 80 + `tls internal` 的 HTTPS 8443 部署，详见 [`docs/deploy-caddy.md`](docs/deploy-caddy.md)。

## App 运行模式（systemd / popen）

应用生命周期支持两种后端：

- `systemd`：由 `.service` 管理 `start/stop/restart/autostart`
- `popen`：使用 Python `subprocess.Popen`（兼容回退）

通过 `$HOME/aivudaOS_ws/config/os.yaml`（或 `$AIVUDAOS_WS_ROOT/config/os.yaml`）的 OS 配置项控制：

- `runtime_process_manager`: `auto` | `systemd` | `popen`（默认 `auto`）
- `runtime_systemd_scope`: `user` | `system`（默认 `user`）

说明：

- `auto`：检测到可用 systemd 时优先使用 systemd，否则自动回退到 `popen`
- `systemd`：优先尝试 systemd；若当前环境不可用会回退到 `popen`
- `popen`：始终使用旧进程模型

日志接口保持不变：`GET /aivuda_os/api/apps/{app_id}/logs` 继续读取 `$HOME/aivudaOS_ws/data/logs/apps/{app_id}/current.log`（或 `$AIVUDAOS_WS_ROOT/data/...`）。

App 启动时会注入配置路径相关环境变量：

- `AIVUDA_APP_CONFIG_PATH`：当前 app 当前版本配置文件路径
- `AIVUDA_APP_ID` / `AIVUDA_APP_VERSION`
- `AIVUDA_APP_HELPERS_ENTRY_PATH`：统一 helper 入口（`core/shell_helpers/aivuda_app_helpers.sh`）

推荐在 app `start.sh` 先 `source "$AIVUDA_APP_HELPERS_ENTRY_PATH"`，再用 `aivuda_yaml_get` 按 dotted path 读取配置。

## 默认账号

- 用户名: `admin`
- 密码: `admin123`

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

## API 接口

### 认证
- `POST /aivuda_os/api/auth/login`
- `GET  /aivuda_os/api/auth/me`

### 配置
- `GET  /aivuda_os/api/config`（`sys.yaml`）
- `PUT  /aivuda_os/api/config`（`sys.yaml`）
- `GET  /aivuda_os/api/config/os`（`os.yaml`）
- `PUT  /aivuda_os/api/config/os`（`os.yaml`）

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
