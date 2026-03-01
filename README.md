# AivudaOS

aivudaOS：部署于机器人机载电脑上的轻量操作系统，用于从 aivudaAppStore 安装和运行应用。

## 目录结构

- `core/`: 核心业务逻辑（纯 Python，不依赖 HTTP）
- `gateway/`: FastAPI 服务层，提供core service的统一的REST 接口，作为后端http server
- `ui/`: 操作界面（Vue 3 + Vite）
- `apps/`: 应用安装目录（多版本，symlink 切换）
- `config/`: YAML 配置文件（OS 全局配置 + 各应用配置）
- `data/`: 运行时数据（数据库、日志、会话、制品缓存）
- `nginx/`: Nginx 配置模板

## 快速启动

### 开发模式（热重载，两个终端）

1. 安装后端依赖

```bash
pip install -r requirements.txt
```

2. 启动 gateway（后端api gateway）

```bash
PYTHONPATH=. uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

3. 启动前端

```bash
cd ui
npm install
npm run dev
```

打开http://localhost:5173/，`/api` 自动代理到 `:8000`（vite.config.js配置了）。

### 生产模式（gunicorn + uvicorn worker）

gateway 启动后自动检测 `ui/dist/`，将前端静态文件与 API 挂载在同一端口。

```bash
# 构建前端静态文件
cd ui && npm install && npm run build && cd ..

# 启动（gunicorn 守护进程 + uvicorn worker）
PYTHONPATH=. gunicorn gateway.main:app -k uvicorn.workers.UvicornWorker -w 1 --bind 0.0.0.0:8000
```

打开 `http://<设备IP>:8000`。本地可以用http://localhost:8000

> **注意**：保持 `-w 1`。安装任务状态存于进程内存，多 worker 会导致任务查询 404。

## Nginx 生产部署（可选）

Nginx 托管前端静态文件并反代 `/api`，详见 [`docs/deploy-nginx.md`](docs/deploy-nginx.md)。

## 远端应用仓库（aivudaAppStore）

应用目录从远端仓库同步，仓库服务由 aivudaAppStore 提供（默认端口 `9001`）。

启动后在 OS 管理界面点击「同步应用目录」，或调用：

```bash
curl -X POST http://localhost:8000/api/apps/repo/sync
```

## App 运行模式（systemd / popen）

应用生命周期支持两种后端：

- `systemd`：由 `.service` 管理 `start/stop/restart/autostart`
- `popen`：使用 Python `subprocess.Popen`（兼容回退）

通过 `config/os.yaml` 的 OS 配置项控制：

- `runtime_process_manager`: `auto` | `systemd` | `popen`（默认 `auto`）
- `runtime_systemd_scope`: `user` | `system`（默认 `user`）

说明：

- `auto`：检测到可用 systemd 时优先使用 systemd，否则自动回退到 `popen`
- `systemd`：优先尝试 systemd；若当前环境不可用会回退到 `popen`
- `popen`：始终使用旧进程模型

日志接口保持不变：`GET /api/apps/{app_id}/logs` 继续读取 `data/logs/apps/{app_id}/current.log`。

## 默认账号

- 用户名: `admin`
- 密码: `admin123`

## 前端路由

| 路径 | 功能 |
|------|------|
| `/login` | 登录 |
| `/status` | 会话状态 |
| `/config` | OS 配置管理 |
| `/apps` | 应用安装 / 版本管理 |

## API 接口

### 认证
- `POST /api/auth/login`
- `GET  /api/auth/me`

### 配置
- `GET  /api/config`
- `PUT  /api/config`

### 应用管理
- `POST /api/apps/repo/sync` — 从仓库同步应用目录
- `GET  /api/apps/catalog` — 可安装应用列表
- `GET  /api/apps/installed` — 已安装应用列表
- `POST /api/apps/{app_id}/install` — 安装应用
- `GET  /api/apps/tasks/{task_id}` — 查询安装任务进度
- `GET  /api/apps/{app_id}/status` — 应用运行状态
- `POST /api/apps/{app_id}/start` — 启动
- `POST /api/apps/{app_id}/stop` — 停止
- `POST /api/apps/{app_id}/autostart` — 设置开机自启
- `GET  /api/apps/{app_id}/versions` — 已安装版本列表
- `POST /api/apps/{app_id}/switch-version` — 切换激活版本
- `POST /api/apps/{app_id}/update_this_version` — 执行指定版本 update_this_version 脚本
- `POST /api/apps/{app_id}/uninstall` — 卸载（支持指定版本或全部）
- `GET /api/apps/operations/{operation_id}` — 查询安装/卸载/更新操作状态
- `GET /api/apps/operations/{operation_id}/events` — SSE 实时操作输出流
- `GET /api/apps/{app_id}/icon` — 获取应用图标（由 manifest `icon` 字段指定，缺省回退默认图标）
- `GET  /api/apps/{app_id}/config` — 读取应用配置
- `PUT  /api/apps/{app_id}/config` — 更新应用配置
