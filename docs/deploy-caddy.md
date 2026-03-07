# Caddy 部署（前端托管 + 后端代理）

本方案用于 `aivudaOS`：

- Caddy 托管前端静态文件（`ui/dist`）
- Caddy 反向代理后端 API（`127.0.0.1:8000`）
- 对外暴露 HTTP `80` 与 HTTPS `8443`

## 1. 安装 Caddy（无 sudo）

推荐在仓库根目录执行：

```bash
bash scripts/install_caddy_local.sh
```

安装完成后验证：

```bash
./.tools/caddy/caddy version
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
bash scripts/run_aivudaos_stack.sh
```

可选：先校验配置再启动。

```bash
./.tools/caddy/caddy validate --config Caddyfile --adapter caddyfile
```

默认监听：

- HTTP: `http://<host>:80`
- HTTPS: `https://<host>:8443`（当前 `tls internal`，浏览器可能提示证书不受信任）

## 4. 用户自启动（backend + caddy 一起）

确保已构建前端后，在仓库根目录执行：

```bash
bash scripts/install_user_services.sh
```

脚本会要求输入两个 HTTPS 地址：

- 公网 IP/域名：`AIVUDAOS_PUBLIC_HTTPS_HOST`
- 内网 IP/域名：`AIVUDAOS_PRIVATE_HTTPS_HOST`

输入内网地址时，脚本会先列出当前服务器检测到的本机 IPv4 地址供选择，也可以手工输入。

脚本会创建并启用单个 `systemd --user` 服务：

- `aivudaos.service`（同时启动 backend + caddy）

由于 `80` 是特权端口，脚本会调用：

```bash
sudo setcap cap_net_bind_service=+ep ./.tools/caddy/caddy
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

- `/aivuda_os/api/apps/operations/{operation_id}/events`（SSE）与
  `/aivuda_os/api/apps/operations/{operation_id}/interactive/ws`（WebSocket）
  均通过 Caddy 转发到后端。

## 6. 重要注意事项

1. 请在 `aivudaOS/` 仓库根目录启动 Caddy（`Caddyfile` 使用相对路径 `./ui/dist`）。
2. 建议后端仅监听 `127.0.0.1:8000`，由 Caddy 统一对外暴露。
3. 当前 `tls internal` 适合内网/开发环境；公网正式域名可改为 ACME 证书模式。