# Streamable HTTP MCP

完成 `aivudaos install` 后，直接运行 `aivudaos-mcp` 或
`python3 -m aivudaos.mcp_server` 启动 MCP；默认通过 Caddy 入口
`http://127.0.0.1/aivuda_os` 调用 API，客户端连接 `http://127.0.0.1:28794/mcp`。

## 传输与调用约定

客户端连接 `http://127.0.0.1:28794/mcp`。这是无会话 Streamable HTTP：
POST 可返回 JSON；通知返回 202；GET 和 DELETE 返回 405；不分配
`Mcp-Session-Id`。支持协议版本 2025-06-18、2025-03-26 和 2024-11-05。
HTTP POST 的 Accept 必须包含 `application/json, text/event-stream`，
Content-Type 为 `application/json`。不需要单独的 SSE 连接。

工具从后端路由生成，名称为路由函数名（原有工具名保留）。`tools/list`
提供参数类型、必填项及 API 方法/路径；JSON 请求体放在 `body` 参数中，
路径、query、header、form 参数使用各自名称。使用 `tools/call` 调用。
所有写操作仍通过后端认证及权限检查，不绕过业务服务。

| 环境变量 | 用途 |
|---|---|
| `AIVUDAOS_MCP_BASE_URL` | Caddy API 入口，默认 `http://127.0.0.1/aivuda_os`，必须包含服务前缀 |
| `AIVUDAOS_MCP_TOKEN` | 可选：显式后端 API token，覆盖自动登录 |
| `AIVUDAOS_MCP_USERNAME` | 自动登录用户名，默认 admin |
| `AIVUDAOS_MCP_PASSWORD` | 自动登录密码，默认 admin123 |
| `AIVUDAOS_MCP_HOST` | MCP 监听地址，默认 127.0.0.1 |
| `AIVUDAOS_MCP_PORT` | MCP 监听端口，默认 28794 |
| `AIVUDAOS_MCP_ACCESS_TOKEN` | MCP 入站 Bearer token，与后端 token 独立 |
| `AIVUDAOS_MCP_ALLOWED_HOSTS` | 可接受的 Host 主机名，逗号分隔 |
| `AIVUDAOS_MCP_ALLOWED_ORIGINS` | 额外允许的 Origin，逗号分隔，默认仅同源 |
| `AIVUDAOS_MCP_MAX_BYTES` | HTTP 请求、上传、后端响应和事件读取的字节上限，默认 64 MiB |

绑定非回环地址必须设置 MCP_ACCESS_TOKEN。远程使用应通过 HTTPS 反向代理，
并根据代理入口设置允许的 Host/Origin。未提供显式 API token 时，受保护调用自动使用默认账号 `admin / admin123` 登录，
token 仅缓存在 MCP 进程内；失效后重新登录并重试一次。公开商店查询不触发登录。
默认/配置账号登录返回 401 后才提示提供当前账号密码；网络或服务错误不会提示修改凭据。
可通过 MCP_USERNAME/MCP_PASSWORD 配置当前账号，或用登录工具取 token 后逐次传入。
显式 token 不会被自动登录替换。API token 可以逐次覆盖；登录返回值
不会保存为整个 MCP 服务的默认账号。上游错误以 MCP `isError` 返回。

文件上传字段使用以下对象；表单中的 JSON 字符串（例如 manifest_json）
仍按原 API 传入字符串：

```json
{
  "package_zip": {
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
或预设 MCP_TOKEN。原有 `aivudaos_status`、`list_installed_apps`、`get_app_status`、
`get_config`、`queue_config_import` 名称保留。

`queue_config_import` 的标准参数为 `body: {"document": {...}, "app_store_base_url": "..."}`；
同时兼容原来顶层 document/app_store_base_url 的调用方式。
`stream_operation_events` 接收 operation_id、token、max_events（1–1000，默认100）、
timeout_seconds（1–60，默认20），返回 events 数组和 timed_out。每次调用从原 API
重新读取事件，客户端按事件 seq 去重；返回的有限批次不表示操作已经完成。
`operation_interactive_ws` 接收 operation_id、token、data，建立上游 WebSocket，
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
PYTHONPATH=. python3 -m unittest discover -s tests -p test_mcp_server.py -v
```
