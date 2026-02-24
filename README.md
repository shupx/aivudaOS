# Drone Orin NX Console MVP

最小可运行版本：`Vue + FastAPI`，包含登录、配置读写、实时状态 WebSocket。

## 目录

- `backend/main.py`: FastAPI 后端
- `backend/requirements.txt`: 后端依赖
- `frontend/`: Vue 前端

## 开发阶段快速启动热修改

1. 安装后端依赖

```bash
python3 -m pip install --user -r backend/requirements.txt
```

2. 启动后端

```bash
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

3. 启动前端开发模式（效率低，但支持热修改；生产部署环境下应改用nginx）

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

打开 `http://<设备IP>:5173`。

## 生产部署（Nginx，HTTP）

目标：Nginx 托管前端静态文件并反代 FastAPI 的 `/api` 与 `/ws`。

1. 构建前端

```bash
export PROJECT_ROOT=/your/path/aivudaOS # 修改为项目实际地址

cd "$PROJECT_ROOT/frontend"
npm ci
npm run build
```

构建产物目录：`$PROJECT_ROOT/frontend/dist`

2. 启动后端（仅监听本机）

```bash
cd "$PROJECT_ROOT"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

3. 安装并启用 Nginx 配置

```bash
sudo apt update
sudo apt install -y nginx

sudo sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  "$PROJECT_ROOT/nginx/aivudaos.conf" \
  > /etc/nginx/sites-available/aivudaos.conf

sudo ln -sf /etc/nginx/sites-available/aivudaos.conf /etc/nginx/sites-enabled/aivudaos.conf
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl reload nginx
```

4. 访问

打开 `http://<设备IP>/`。 （默认http转到80端口，因此不用写端口）

更多细节见：`docs/deploy-nginx.md`。

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
