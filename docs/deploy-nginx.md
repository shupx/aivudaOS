# Nginx 部署说明（主机直装，HTTP）

目标：Nginx 托管前端静态文件并反代 FastAPI 的 `/api` 与 `/ws`，实现单端口对外服务。

- Nginx 提供前端静态文件与 SPA 路由
- Nginx 反代 FastAPI 的 `/api/*` 与 `/ws/*`
- 后端仅监听 `127.0.0.1:8000`

## 1. 前置条件

- 系统：Ubuntu/Debian（其他发行版替换对应包管理命令）
- 项目路径：任意目录（以下使用环境变量 `PROJECT_ROOT`）
- 已安装 Python 3 与 Node.js

## 2. 构建前端

```bash
export PROJECT_ROOT=/your/path/aivudaOS  # 修改为项目实际路径
cd "$PROJECT_ROOT/ui"
npm ci
npm run build
```

产物目录：`$PROJECT_ROOT/ui/dist`

## 3. 启动后端

```bash
cd "$PROJECT_ROOT"
PYTHONPATH=. gunicorn gateway.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 1 \
  --bind 127.0.0.1:8000
```

说明：监听 `127.0.0.1`，由 Nginx 对外暴露服务。

> **注意**：保持 `-w 1`。安装任务状态存于进程内存，多 worker 会导致任务查询 404。

## 4. 安装并配置 Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

复制仓库内站点配置：

```bash
# 将模板中的 __PROJECT_ROOT__ 替换为实际路径后写入 Nginx 配置
sudo sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  "$PROJECT_ROOT/nginx/aivudaos.conf" \
  > /etc/nginx/sites-available/aivudaos.conf

sudo ln -sf /etc/nginx/sites-available/aivudaos.conf /etc/nginx/sites-enabled/aivudaos.conf
sudo rm -f /etc/nginx/sites-enabled/default
```

验证并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 5. 验证

1. 打开 `http://<设备IP>/`，可看到前端页面
2. 登录后功能正常：
   - `/api/auth/me`
   - `/api/config`
   - `/api/status/snapshot`
3. WebSocket 正常：
   - `ws://<设备IP>/ws/telemetry?token=...`
4. 页面刷新 `/status`、`/config` 不应出现 404

## 6. 常见检查命令

检查 Nginx 配置语法：

```bash
sudo nginx -t
```

查看 Nginx 服务状态：

```bash
sudo systemctl status nginx
```

检查后端端口监听：

```bash
ss -lntp | grep 8000
```

## 7. 可选：systemd 管理后端

可新建 `/etc/systemd/system/aivudaos-backend.service`：

```ini
[Unit]
Description=aivudaOS FastAPI backend
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/your/path/aivudaOS
Environment=PYTHONPATH=.
ExecStart=/usr/bin/python3 -m gunicorn gateway.main:app -k uvicorn.workers.UvicornWorker -w 1 --bind 127.0.0.1:8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用方式：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aivudaos-backend
sudo systemctl status aivudaos-backend
```

## 8. 说明

- 当前文档不包含 HTTPS（443）与证书申请。
- 若后续接入证书，可在此配置基础上新增 443 `server` 块并将 80 跳转到 443。
