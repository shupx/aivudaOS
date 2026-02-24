# Drone Orin NX Console MVP

最小可运行版本：`Vue + FastAPI`，包含登录、配置读写、实时状态 WebSocket。

## 目录

- `backend/main.py`: FastAPI 后端
- `backend/requirements.txt`: 后端依赖
- `frontend/`: Vue 前端

## 快速启动

1. 安装后端依赖

```bash
python3 -m pip install --user -r backend/requirements.txt
```

2. 启动后端

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

3. 启动前端开发模式

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

打开 `http://<设备IP>:5173`。

## 默认账号

- 用户名: `admin`
- 密码: `admin123`

## 前端路由

- `/login`: 登录页
- `/status`: 实时状态
- `/config`: 配置管理

## 接口

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/status/snapshot`
- `WS /ws/telemetry`

## 说明

- 当前为 MVP，认证令牌和用户数据使用内存/本地 SQLite 简化实现。
- 生产环境建议加 HTTPS、密码哈希、权限细化、审计日志与 systemd 自启。
