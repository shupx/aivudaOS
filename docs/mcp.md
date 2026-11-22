# 内置 Streamable HTTP MCP

MCP 是 AivudaOS FastAPI 后端的一部分，随主服务启动、关闭，无需单独命令、
监听端口或代理站点。统一路径为 `/aivuda_os/mcp`：

- standalone 本机：`http://127.0.0.1/aivuda_os/mcp`
- standalone 远端：`https://<avahi_hostname>.local/aivuda_os/mcp`
- ACEswarm：`http://127.0.0.1:28790/aivuda_os/mcp`（随 `ACESWARM_GATEWAY_PORT`）

HTTP 和 HTTPS 站点共用 Caddy 路由，均转发到同一个后端。内部通过 ASGI
请求同一 FastAPI 应用的 `/aivuda_os/api/...`，保留路由、middleware、参数校验、
认证和业务权限检查；不访问客户端提供的 Host，不回连 Caddy，也不需要信任
自己的 HTTPS 证书。远端客户端仍需信任 Caddy 的本地 CA。

原 `aivudaos-mcp` 命令和 `python -m aivudaos.mcp_server` 启动方式已移除，
客户端应将旧 `:28794/mcp` 地址改为上述入口。主服务启动时会为旧包内
`@api path /aivuda_os/api*` matcher 补充 MCP 路径；自定义 matcher 需自行加入
`/aivuda_os/mcp`。ACEswarm 重新生成网关配置时也会加入该路径。

## 传输与调用约定

客户端连接 `/aivuda_os/mcp`。这是无会话 Streamable HTTP：
POST 可返回 JSON；通知返回 202；GET 和 DELETE 返回 405；不分配
`Mcp-Session-Id`。支持协议版本 2025-06-18、2025-03-26 和 2024-11-05。
HTTP POST 的 Accept 必须包含 `application/json, text/event-stream`，
Content-Type 为 `application/json`。不需要单独的 SSE 连接。

工具从后端路由生成，名称为路由函数名（原有工具名保留）。`tools/list`
提供参数类型、必填项及 API 方法/路径；JSON 请求体放在 `body` 参数中，
路径、query、header、form 参数使用各自名称。使用 `tools/call` 调用。
所有写操作仍通过后端认证及权限检查，不绕过业务服务。

## 认证与请求隔离

agent 先直接调用工具，不必预先向用户索要 token 或账号密码。未显式提供
API token 时，内置 MCP 自动使用 `admin / admin123` 登录，临时 token 缓存在
主进程内，并发调用共用一次登录。受保护 API 返回 401 时，自动重新登录并
重试一次；不会无限重试。

只有默认/配置账号登录返回 401 时，才提示 agent 向用户获取当前用户名和密码：

1. 调用 `login`，参数 `body: {"username": "...", "password": "..."}`。
2. 从结果读取 `access_token`。
3. 后续工具参数传 `token`，或为 MCP HTTP 请求设置
   `Authorization: Bearer <access_token>`。显式工具 token 优先于请求头。

网络/服务故障不会提示修改账号密码。显式 token 被拒绝时不会自动替换为默认
账号；手动登录和请求头身份不会改变共享的自动登录账号。自动 token 只存在于
MCP 进程内，客户端身份和 ASGI 传输仍按请求隔离；浏览器登录不认证 MCP。
请求头 Authorization 格式错误返回 HTTP 401。

`AIVUDAOS_MCP_USERNAME` / `AIVUDAOS_MCP_PASSWORD` 可覆盖自动登录账号；
`AIVUDAOS_MCP_TOKEN` 可配置显式 API token，失效时不会自动替换。
不再使用 `AIVUDAOS_MCP_HOST`、`PORT`、`BASE_URL`、`ACCESS_TOKEN`、
`ALLOWED_HOSTS` 或 `ALLOWED_ORIGINS` 配置内置 MCP。
入口跟随 Caddy 站点；有 Origin 的请求必须与当前入口完全同源，跨源请求返回
403。生产部署应保持后端为回环监听，由可信 Caddy 处理入口及转发协议。

`AIVUDAOS_MCP_MAX_BYTES` 仍控制 HTTP 请求、上传、响应和事件读取上限，默认
64 MiB。MCP 不持有额外监听资源，内部请求结束、超时或失败后关闭 ASGI 请求；
事件流按事件数和期限读取，交互 WebSocket 完成一次输入/回复后关闭。

文件上传字段使用以下对象；表单中的 JSON 字符串（例如 manifest_json）
仍按原 API 传入字符串：

```json
{
  "file": {
    "filename": "app.zip",
    "content_type": "application/zip",
    "content_base64": "UEsDB..."
  }
}
```

文件字段名称以工具 schema 为准。下载返回原始 `filename`、`content_base64`、`content_type`、
`content_disposition` 和 `size`；HEAD 返回状态和响应头。MCP 不读取调用者
指定的服务器本地路径。超限文件使用原 HTTP API，或提高字节上限；base64
以及 JSON/multipart 包装也占用字节额度。

目前提供 47 个工具，覆盖 46 个 HTTP 操作和 1 个 WebSocket 操作。
`login` 接收 `body: {"username": "...", "password": "..."}`；之后传入 `token`，
或通过 MCP HTTP Bearer 请求头传递。原有 `aivudaos_status`、`list_installed_apps`、`get_app_status`、
`get_config`、`queue_config_import` 名称保留。

`queue_config_import` 的标准参数为 `body: {"document": {...}, "app_store_base_url": "..."}`；
同时兼容原来顶层 document/app_store_base_url 的调用方式。
`stream_operation_events` 接收 operation_id、token、max_events（1–1000，默认100）、
timeout_seconds（1–60，默认20），返回 events 数组和 timed_out。每次调用通过内部 ASGI 从原 API
重新读取事件，客户端按事件 seq 去重；返回的有限批次不表示操作已经完成。
`operation_interactive_ws` 接收 operation_id、token、data，建立内部 ASGI WebSocket，
读取 ready、发送输入、读取 reply 后关闭连接；输出日志继续通过事件工具读取。

## 完整工具清单

目前共 47 个工具，按用途分组如下。具体参数、类型和必填项以 `tools/list`
返回的 `inputSchema` 为准；新增后端路由后，工具列表会随之更新。

| 用途 | Tools |
|---|---|
| 登录与身份 | `login`、`me` |
| 配置与导入 | `get_config`、`put_config`、`get_os_config`、`put_os_config`、`queue_config_import`、`get_config_export_meta` |
| 磁铁配置 | `list_magnets`、`update_magnet` |
| 系统服务 | `aivudaos_status`、`set_aivudaos_service_autostart`、`trigger_aivudaos_service_action`、`relogin_system_user`、`restart_avahi` |
| sudo 免密 | `get_sudo_nopasswd`、`put_sudo_nopasswd` |
| APT 源与备份 | `get_apt_sources_list`、`put_apt_sources_list`、`list_apt_sources_backups`、`restore_apt_sources_list` |
| 证书 | `download_caddy_local_ca_root`、`download_caddy_local_ca_root_head` |
| 应用信息与日志 | `list_installed_apps`、`get_active_configs`、`get_app_status`、`get_app_icon`、`get_logs` |
| 应用运行控制 | `start_app`、`stop_app`、`restart_app`、`set_autostart` |
| 批量运行控制 | `start_autostart_apps`、`restart_autostart_apps`、`stop_all_apps` |
| 安装与版本管理 | `upload_app`、`list_versions`、`switch_version`、`update_this_version`、`upgrade_app`、`uninstall_app` |
| 应用配置 | `get_app_config`、`put_app_config` |
| 异步操作与交互 | `get_operation`、`cancel_operation`、`stream_operation_events`、`operation_interactive_ws` |

## 验证

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_mcp*.py' -v
```

`test_mcp_gateway.py` 在存在 ACEswarm 开发 Caddy 二进制时启动隔离后端及
Caddy，使用包内模板验证 HTTP 和 HTTPS、CA 证书信任、同源 Origin、登录、
Bearer 调用及退出端口释放；不安装 CA 到系统信任库。
