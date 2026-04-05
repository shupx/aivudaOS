# Caddy 部署（前端托管 + 后端代理）

本方案用于 `aivudaOS`：

- Caddy 托管前端静态文件（`ui/dist`）
- Caddy 反向代理后端 API（`127.0.0.1:8000`）
- 对外暴露 HTTP `80` 与 HTTPS `443`

> 本项目用caddy而不是nginx，是因为caddy配置https tls证书和websocket反代更简单，caddyfile比nginx config好写

## 1. 安装 Caddy（无 sudo）

推荐在仓库根目录执行：

```bash
bash scripts/_download_caddy.sh
```

安装完成后验证：

```bash
cd ~
./aivudaOS_ws/.tools/caddy/caddy -v
```

## 2. 构建前端

在仓库根目录执行：

```bash
cd ui
npm install
npm run build
```

构建产物默认在 `ui/dist`。

## 3. 启动后端 + Caddy（前台）

在仓库根目录执行：

```bash
bash scripts/_run_aivudaos_stack.sh
```

可选：先校验配置再启动。

```bash
./aivudaOS_ws/.tools/caddy/caddy validate --config "${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile" --adapter caddyfile
```

默认监听：

- HTTP: `http://127.0.0.1:80`（仅本机）
- HTTPS: `https://<avahi_hostname>.local:443`（当前 `tls internal`，浏览器可能提示证书不受信任）

## 4. 用户自启动（backend + caddy 一起）

确保已构建前端后，在仓库根目录执行:

```bash
bash scripts/install_user_services.sh
```

脚本会自动：

- 在 Debian/Ubuntu（`apt-get` 可用）安装 `avahi-daemon` 与 `avahi-utils`
- 为当前用户配置 sudo 免密（`/etc/sudoers.d/$USER`，幂等）
- 从 `~/aivudaOS_ws/config/os.yaml` 的 `avahi_hostname` 读取主机名，若不存在则自动生成 `robot-xxx`
- 将主机名写入 `/etc/avahi/avahi-daemon.conf` 的 `[server]` 块 `host-name=<value>` 并重启 `avahi-daemon.service`
- 将 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile` 的 HTTPS 站点写成具体 `https://<hostname>.local:443`（不使用环境变量占位）
- 当主机名变更导致 Caddyfile 内容变化时，自动执行一次 caddy reload

脚本会创建并启用单个 `systemd --user` 服务：

- `aivudaos.service`（同时启动 backend + caddy）

由于 `80` 是特权端口，脚本会调用：

```bash
sudo setcap cap_net_bind_service=+ep ${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/.tools/caddy/caddy
```

并自动执行“未登录也自启动”配置（需管理员权限）：

```bash
sudo loginctl enable-linger $USER
```

常用命令：

```bash
systemctl --user status aivudaos.service
systemctl --user restart aivudaos.service
systemctl --user stop aivudaos.service
journalctl --user -u aivudaos.service -f
```

## 5. 路由行为

- `/aivuda_os/api/*` -> 反代到 `127.0.0.1:8000`
- 其他路径 -> 前端静态资源，SPA 回退到 `/index.html`

说明：

- HTTP 站点仅绑定 `127.0.0.1:80`，不对外网/局域网暴露。
- `/aivuda_os/api/apps/operations/{operation_id}/events`（SSE）与
  `/aivuda_os/api/apps/operations/{operation_id}/interactive/ws`（WebSocket）
  均通过 Caddy 转发到后端。
- 运行中若通过 `PUT /aivuda_os/api/config/os` 修改 `avahi_hostname`，后端会立即把 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile` 的 HTTPS host 同步为新的 `<avahi_hostname>.local`，并在 Caddy 正在运行时尝试 reload。

## 6. 重要注意事项

1. 运行时 Caddy 配置文件是 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/Caddyfile`，首次启动会从仓库模板 `aivudaOS/Caddyfile_template` 自动复制。
2. 建议后端仅监听 `127.0.0.1:8000`，由 Caddy 统一对外暴露。
3. 当前 `tls internal` 适合内网/开发环境；公网正式域名可改为 ACME 证书模式。