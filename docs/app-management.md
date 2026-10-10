# AivudaOS App 管理

## 概述

AivudaOS 通过 **本地上传安装包** 的方式管理应用。每个 App 以 `.tar.gz`、`.tgz`、`.tar`、`.tar.xz`、`.txz` 或 `.zip` 压缩包上传，包内必须包含 `manifest.yaml` 描述文件。系统支持多版本共存、版本切换、进程生命周期管理和自启动。

当前 UI 还支持“在线应用商店”入口：从 aivudaAppStore 的 `store` API 查看应用与版本，先下载安装包到浏览器本机，再一键上传到 AivudaOS 安装。

当前 UI 新增“配置参数”中心入口（Dashboard 侧边栏），统一管理所有已安装 app 的 **active 版本** 配置。各 app 详情页仅保留跳转到统一参数中心，不再提供分散编辑入口。

前端 UI 支持 `zh-CN / en-US` 语言切换（Dashboard 左侧栏入口），并将选择持久化到本地存储。当前版本只对前端固定文案做国际化，后端返回的动态文本（如 SSE 日志、错误详情）按原文显示。

App 的 `start / stop / restart` 与批量 `restart-autostart / start-autostart / stop-all` 现在会先返回 queued operation，由后台线程并行执行；同一 app 仍然保留单操作冲突保护。

### 参数弹窗复制

参数中心的默认值弹窗及数组/对象编辑弹窗共用 `aivudaos/resources/ui/src/services/core/clipboard.js`：优先使用 Clipboard API，在 API 缺失（非安全 HTTP）或被 Electron WebView 权限拒绝时，降级为文本选区复制；失败显示国际化提示。默认值弹窗逻辑位于 `aivudaos/resources/ui/src/composables/useDefaultValueModal.js`。


参数表列宽及拖拽分隔线统一由 `useResizableConfigTable` 管理；列位置未变化时不写响应式状态，避免 `onUpdated → requestAnimationFrame → 新数组 → onUpdated` 的空闲刷新循环。表格异步出现后自动绑定滚动和尺寸监听，离开页面时清理。回归验证：`node --test tests/test_config_table_layout.mjs`（需先安装 UI 依赖）。

## 核心模块

| 模块 | 路径 | 职责 |
|---|---|---|
| InstallerService | `core/apps/installer.py` | 解压安装包、解析 manifest、写入文件和数据库 |
| VersioningService | `core/apps/versioning.py` | 多版本目录管理、symlink 切换 |
| RuntimeService | `core/apps/runtime.py` | 启动/停止/重启、autostart、卸载 |
| SystemdRuntimeBackend | `core/apps/systemd_runtime.py` | systemd 单元生成与 systemctl 调用 |
| ConfigService | `core/config/service.py` | 每个 App 的 YAML 配置读写 |

依赖注入在 `gateway/deps.py`，API 路由在 `gateway/routes/apps.py`。

## 安装包格式

```
my-app-1.0.0.tar.gz
├── manifest.yaml        # 必须
├── start.sh             # 入口脚本
├── assets/
│   └── icon.png         # 可选，应用图标
└── ...                  # 其他应用文件
```

> 支持包内有一层包裹目录（如 `my-app/manifest.yaml`），系统会自动向下查找。
> 安装时会校验 `run.entrypoint` 是否存在，并自动补齐可执行权限（`chmod +x`）。
> App 图标由 manifest 的 `icon` 字段指定（可选）；未指定或文件不存在时使用默认图标。
> App 内置 UI 入口由 manifest 的 `ui_index_path` 字段指定（可选）；未指定时前端不显示“进入内置 UI”。
> 若内置 UI 是 qiankun 子应用，可额外设置 `ui_mount_type: qiankun`，使其被 PanelHub 自动发现并尝试挂载。

### manifest.yaml 字段

```yaml
app_id: my-app                 # 唯一标识（必填）
name: My App                   # 显示名称
version: 1.0.0                 # 版本号（必填）
description: 一个示例应用
run:
  entrypoint: ./start.sh       # 启动入口（必填）
  args: []                     # 启动参数
icon: ./assets/icon.png        # 应用图标路径（可选，相对安装根目录）
ui_index_path: ui/index.html   # 应用内置 UI 首页（可选，相对安装根目录）
ui_mount_type: qiankun         # 声明该内置 UI 可被 PanelHub 作为 qiankun 子应用挂载（可选）
pre_install: ./scripts/pre_install.sh      # 安装前脚本（可选）
pre_uninstall: ./scripts/pre_uninstall.sh  # 卸载前脚本（可选）
update_this_version: ./scripts/update_this_version.sh # update_this_version 脚本（可选）
default_config_path: ./config/default_config.yaml   # 默认配置文件（必填，包内相对路径）
config_schema_path: ./config/config_schema.yaml     # schema 文件（必填，包内相对路径）
```

### 配置 schema 规范（统一参数中心使用）

`config_schema_path` 建议使用 JSON Schema 子集（YAML/JSON 均可），统一参数中心会优先按以下字段表格化展示：

- 基础：`type`、`default`、`description`
- 对象：`properties`、`required`、`additionalProperties`
- 枚举：`enum`
- 数值范围：`minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`
- 字符串范围：`minLength`、`maxLength`、`pattern`
- 数组范围：`items`、`minItems`、`maxItems`

后端在配置保存时会校验上述范围约束；未提供的字段在统一参数中心显示为 `-`。

### App 内置 UI 托管

- manifest `ui_index_path` 指向 app 包内首页文件（例如 `./ui/index.html`）
- 内置 UI 路径统一为 `/{app_id}/ui/` 与 `/{app_id}/ui/*`
- 该路径不再由 FastAPI `FileResponse` 提供，而是由 Caddy 静态托管
- 系统会在 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/caddy/` 自动生成 `{app_id}.ui.caddy`
- 安装、卸载、切换版本时会自动更新顶层 Caddyfile import 区块并 reload Caddy
- 设置 `ui_mount_type: qiankun` 后，该入口会继续作为普通 built-in UI 可访问，同时会在 PanelHub 自动发现列表中被标记为可挂载

### 可选生命周期脚本

- `pre_install`：安装时执行（严格模式，非 0 返回码会中断安装）
- `pre_uninstall`：卸载时执行（严格模式，非 0 返回码会中断卸载）
- `update_this_version`：通过 API 手动触发的版本更新脚本（严格模式）


脚本执行规则：

- 脚本字段为安装包内相对路径
- pre_install 在最终版本目录中执行（不是上传临时目录）
- pre_install 结束后会重新读取 `config_schema_path` 与 `default_config_path`，并用最新 schema 校验 default，因此脚本可动态生成或修改 schema 和默认配置
- 执行前会自动补齐可执行权限（`chmod +x`）
- 不设置超时，允许用户手动终止
- 输出写入 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/data/logs/os/install.log`
- 同时通过操作事件流实时回传到前端
- `pre_install` 支持 PTY 交互模式（可接收 sudo 密码、`y/n` 等输入）

覆盖安装（同版本 `overwrite=true`）时，会先重建该版本目录，再执行 pre_install。


## 文件系统布局
默认运行时根目录：`$HOME/aivudaOS_ws`（可通过环境变量 `AIVUDAOS_WS_ROOT` 覆盖）。

配置说明：

- `config/os.yaml`：系统运行参数（如 `runtime_process_manager`、`runtime_systemd_scope`、`avahi_hostname`），不参与磁吸。
- `config/sys.yaml`：公用业务参数（支持增删改），参与磁吸；默认包含 `role.id=1`。active app 的 schema 中若声明 `sys.*` 参数（如 `sys.robot_type`、`sys.aaa.bbb`），磁吸重算会在缺失时自动补齐到 System Parameters，并保留对应 schema 以便 UI 展示类型/范围/描述。这些自动补齐的 system parameters 不会因为 app 卸载、删除或切换 active 版本而自动删除。

```
${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/
├── apps/                          # 所有 App 安装目录
│   └── {app_id}/
│       ├── versions/
│       │   ├── 1.0.0/            # 版本目录（实际文件）
│       │   └── 1.1.0/
│       └── active -> versions/1.1.0   # symlink 指向当前激活版本
├── config/
│   ├── caddy/
│   │   └── {app_id}.ui.caddy      # 自动生成的 app 内置 UI 托管片段
│   └── apps/
│       └── {app_id}/
│           └── {version}/
│               ├── {version}.yaml            # 活跃配置（用户修改）
│               └── {version}_default.yaml    # 包默认配置（每次安装覆盖）
├── data/
│   ├── aivuda.db                 # SQLite 数据库
│   ├── uploads/                  # 上传临时目录
│   └── runtime/
│       └── {app_id}/
│           └── {version}/        # 每个 app 每个版本独立 runtime 数据目录
```

## 数据库表

### app_installation

| 列 | 类型 | 说明 |
|---|---|---|
| app_id | TEXT | App 唯一标识（联合主键） |
| version | TEXT | 版本号（联合主键） |
| install_path | TEXT | 版本目录绝对路径 |
| status | TEXT | 安装状态（`installed`） |
| installed_at | INTEGER | 安装时间戳 |
| manifest | TEXT | manifest JSON 全文 |

### app_runtime

| 列 | 类型 | 说明 |
|---|---|---|
| app_id | TEXT | 主键 |
| running | INTEGER | 是否正在运行（0/1） |
| autostart | INTEGER | 是否自启动（0/1） |
| pid | INTEGER | 进程 PID |
| last_started_at | INTEGER | 上次启动时间戳 |
| last_stopped_at | INTEGER | 上次停止时间戳 |

## 安装流程

```
上传 .tar.gz / .zip
       │
       ▼
  解压到临时目录
       │
       ▼
  查找 manifest.yaml（根目录或一级子目录）
       │
       ▼
  解析 → AppManifest 对象
       │
       ▼
  读取 default_config_path + config_schema_path（必须在包内）
       │
       ▼
  校验 default_config 是否满足 config_schema
       │
       ▼
     创建版本目录 ${AIVUDAOS_WS_ROOT}/apps/{app_id}/versions/{version}/
       │
       ▼
  复制所有文件到版本目录
       │
       ▼
  执行 pre_install（如有）后重新读取 config_schema_path + default_config_path
       │
       ▼
  写入 app_installation 表 + app_runtime 表
       │
       ▼
           初始化 ${AIVUDAOS_WS_ROOT}/config/apps/{app_id}/{version}/{version}.yaml
                + 写入 ${AIVUDAOS_WS_ROOT}/config/apps/{app_id}/{version}/{version}_default.yaml
       │
       ▼
     创建 symlink: ${AIVUDAOS_WS_ROOT}/apps/{app_id}/active → versions/{version}
```

## 运行时管理

运行时支持两种模式，由 `${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/os.yaml` 决定：

- `runtime_process_manager`: `auto` | `systemd` | `popen`
- `runtime_systemd_scope`: `user` | `system`
- `runtime_environment`: 所有 app 共用的额外环境变量字符串映射，默认 `{ROS_LOCALHOST_ONLY: "1"}`；允许显式清空为 `{}`
- `avahi_hostname`: mDNS 主机名（默认自动生成 `robot-xxx`）

### systemd 模式（优先）

- 启动/停止/重启通过 `systemctl` 调用对应 `.service`
- 自启动对应 `systemctl enable/disable`
- 状态由 `systemctl show` 查询并同步到 `app_runtime`
- 单元名格式：`aivuda-app-{app_id}.service`（会做安全规范化）

### 生命周期调度

- 单个 app 的 `start / stop / restart` 会被包装成后台 operation，接口返回后立即结束
- 批量操作会为每个 app 创建独立 operation 并并行执行
- 操作状态通过 `GET /api/apps/operations/{operation_id}` 和 `GET /api/apps/operations/{operation_id}/events` 查询

### popen 回退模式

- **启动**：根据 `manifest.run.entrypoint` 构建命令，`subprocess.Popen` 启动（`start_new_session=True`）
- 运行时会统一注入日志实时输出环境（例如 `PYTHONUNBUFFERED=1`、`ROSCONSOLE_STDOUT_LINE_BUFFERED=1`），并在可用时自动使用 `stdbuf -oL -eL` 包装启动命令，减少日志缓冲延迟
- 运行时会注入配置文件路径相关环境变量：
     - `AIVUDA_APP_CONFIG_PATH`：当前 app 当前版本的配置文件路径（例如 `${AIVUDAOS_WS_ROOT}/config/apps/{app_id}/{version}/{version}.yaml`）
     - `AIVUDA_APP_ID` / `AIVUDA_APP_VERSION`：当前 app 标识与版本
     - `AIVUDA_APP_INSTALL_PATH`：当前 app 当前版本安装目录（例如 `${AIVUDAOS_WS_ROOT}/apps/{app_id}/versions/{version}`）
     - `AIVUDA_APP_RUNTIME_DATA_PATH`：当前 app 当前版本 runtime 数据目录（例如 `${AIVUDAOS_WS_ROOT}/data/runtime/{app_id}/{version}`）
     - `AIVUDA_APP_HELPERS_ENTRY_PATH`：统一 helper 入口（`aivudaos/resources/shell_helpers/aivuda_app_helpers.sh`）
- app 启动脚本建议先 `source "$AIVUDA_APP_HELPERS_ENTRY_PATH"`
- 之后可调用 `aivuda_yaml_get <dotted.path> [default]` 与 `aivuda_yaml_has <dotted.path>`
- **停止**：`os.kill(pid, SIGTERM)`
- PID 记录在 `app_runtime` 表
- 进程自然退出时会自动回写 `app_runtime`：`running=0`、`pid=NULL`、更新 `last_stopped_at`

### 自启动（Autostart）

通过 `POST /aivuda_os/api/apps/{app_id}/autostart` 设置：

- systemd 模式：更新 unit 的 enabled 状态，同时同步 `app_runtime.autostart`
- popen 模式：仅更新 `app_runtime.autostart`，由后端启动时回放拉起

后端启动阶段：

- systemd 模式：跳过 DB 自启动回放（由 systemd 自身管理）
- popen 模式：扫描 `autostart=1` 并执行 `start()`

## API 端点

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/aivuda_os/api/apps/upload` | 上传安装包（首次安装） |
| POST | `/aivuda_os/api/apps/{app_id}/upgrade` | 上传新版本（升级，若正在运行则自动重启） |
| POST | `/aivuda_os/api/apps/{app_id}/update_this_version` | 执行指定已安装版本的 `update_this_version` 脚本 |
| GET | `/aivuda_os/api/apps/operations/{operation_id}` | 查询操作状态 |
| GET | `/aivuda_os/api/apps/operations/{operation_id}/events` | SSE 实时事件流 |
| POST | `/aivuda_os/api/apps/operations/{operation_id}/cancel` | 取消运行中的操作 |
| WS | `/aivuda_os/api/apps/operations/{operation_id}/interactive/ws?token=...` | 交互输入通道（写入脚本 stdin） |
| GET | `/aivuda_os/api/apps/installed` | 已安装应用列表 |
| GET | `/aivuda_os/api/apps/{app_id}/status` | 应用详情（安装信息 + 运行状态） |
| GET | `/aivuda_os/api/apps/{app_id}/ui/?token=...` | 获取应用内置 UI 首页 |
| GET | `/aivuda_os/api/apps/{app_id}/ui/{asset_path}?token=...` | 获取内置 UI 静态资源 |
| POST | `/aivuda_os/api/apps/{app_id}/start` | 启动 |
| POST | `/aivuda_os/api/apps/{app_id}/stop` | 停止 |
| POST | `/aivuda_os/api/apps/{app_id}/restart` | 重启 |
| POST | `/aivuda_os/api/apps/{app_id}/autostart` | 设置自启动 `{ "enabled": true }` |
| GET | `/aivuda_os/api/apps/{app_id}/versions` | 版本列表 |
| POST | `/aivuda_os/api/apps/{app_id}/switch-version` | 切换版本 `{ "version": "1.0.0", "restart": true }` |
| POST | `/aivuda_os/api/apps/{app_id}/uninstall` | 卸载 `{ "purge": false, "version": null }` |
| GET | `/aivuda_os/api/apps/{app_id}/config` | 获取 App 配置（可选 query: `app_version`） |
| PUT | `/aivuda_os/api/apps/{app_id}/config` | 更新 App 配置 `{ "version": 1, "app_version": "1.0.0", "data": {...} }` |
| GET | `/aivuda_os/api/apps/configs/active` | 获取全部已安装 app 的 active 配置、schema、约束（统一参数中心） |
| GET | `/aivuda_os/api/config/system/sudo-nopasswd` | 获取当前系统用户 sudo 免密状态 |
| PUT | `/aivuda_os/api/config/system/sudo-nopasswd` | 设置当前系统用户 sudo 免密（需 sudo 密码） |
| POST | `/aivuda_os/api/config/system/relogin` | 注销当前 token 并后台执行 `sudo systemctl restart user@$(id -u $USER).service` |
| POST | `/aivuda_os/api/config/system/avahi/restart` | 重启 `avahi-daemon.service` |
| GET | `/aivuda_os/api/config/system/aivudaos-service` | 查询 AivudaOS 自身 user service 的安装/运行/自启动状态 |
| POST | `/aivuda_os/api/config/system/aivudaos-service/autostart` | 设置 AivudaOS 自身自启动 `{ "enabled": true }` |
| POST | `/aivuda_os/api/config/system/aivudaos-service/{action}` | 触发 `stop` / `restart` / `uninstall`，以脱离当前服务生命周期的后台脚本执行 |
| GET | `/aivuda_os/api/config/system/apt-sources-list` | 自动检测并读取 Ubuntu 主源文件，返回 `path` 和 `format` |
| GET | `/aivuda_os/api/config/system/apt-sources-list/backups` | 获取 APT 源时间戳备份列表 |
| PUT | `/aivuda_os/api/config/system/apt-sources-list` | 写入 APT 源（写入前自动备份，并执行 `apt update`） |
| POST | `/aivuda_os/api/config/system/apt-sources-list/restore` | 按备份版本恢复 APT 源，并执行 `apt update` |

> 所有端点需要 `token` 参数进行身份验证。

## 在线应用商店流程

1. 在 UI 的“在线应用商店”页面设置商店地址（保存到浏览器 localStorage，key: `aivuda_ui_appstore_base_url`）。
2. 前端调用：`{appstore_base_url}/aivuda_app_store/store/index` 获取应用卡片列表。
3. 点击应用后调用：`.../store/apps/{app_id}` 查看版本详情。
4. 点击“下载到本机”后，前端调用 `.../download-url` 与 `.../download`，将安装包下载到浏览器本机。
5. 点击“安装到 AivudaOS”后，前端把该下载文件通过 `POST /aivuda_os/api/apps/upload` 上传给本机 AivudaOS，安装流程与手动上传一致。

当前在线商店页已改为单按钮“下载并安装到 AivudaOS”流程：

1. 先触发浏览器原生下载，保存到用户指定的本机位置（由浏览器下载设置决定）。
2. 随后询问是否立即安装。
3. 若确认，打开与“手动上传新应用安装包”完全复用的上传安装弹窗。
4. 用户在弹窗中选择刚下载的本机文件并提交安装，后端仍走 `POST /aivuda_os/api/apps/upload` 同一流程。

### 实时操作事件（SSE）

`POST /aivuda_os/api/apps/upload`、`POST /aivuda_os/api/apps/{app_id}/uninstall`、`POST /aivuda_os/api/apps/{app_id}/update_this_version` 现在返回：

```json
{
     "ok": true,
     "operation_id": "...",
     "status": "queued"
}
```

前端随后连接：

`GET /aivuda_os/api/apps/operations/{operation_id}/events?token=...`

典型事件：

- `status`：阶段状态（prepare/extract/pre_install/remove/completed 等）
- `log`：脚本输出逐行内容（stdout/stderr）
- `error`：失败信息
- `completed`：操作结束（成功或失败）

### 交互安装输入（WS）

`POST /aivuda_os/api/apps/upload` 的响应包含：

- `interactive_enabled`: 是否支持交互
- `interactive_ws_path`: WebSocket 路径

前端建议并行建立两条链路：

1. SSE 接收状态与日志输出（只读）
2. WS 发送交互输入（可写）

输入协议：

- 客户端可发送纯文本，或 JSON `{ "type": "input", "data": "..." }`
- 后端会自动补 `\n` 后写入脚本 stdin
- 空输入（例如仅按 Enter，发送空字符串）也会被接受，并作为换行写入脚本 stdin
- 任务结束后交互会话自动关闭

取消操作：

- 前端可调用 `POST /operations/{operation_id}/cancel` 请求取消
- 服务端会将状态置为 `cancelling`，并在脚本退出后结束为 `canceled`

## 版本管理

- 同一 App 可安装多个版本，共存于 `apps/{app_id}/versions/` 下
- `active` symlink 指向当前激活版本
- `switch-version` 可切换激活版本，可选自动重启
- `uninstall` 可删除单个版本或整个 App（`purge=true` 同时删除配置）
- 卸载版本或整应用时，会同步删除 `${AIVUDAOS_WS_ROOT}/data/runtime/{app_id}/{version}`（或整个 `{app_id}`）目录

## 参数尽量迁移

文件布局不变：每个版本分别保存自己的 `{version}.yaml`、`{version}_default.yaml` 和 schema。
升级及切换（包括切回旧版本）均从操作前 active 版本迁移参数；覆盖安装使用被覆盖版本
原有参数，不使用其他 active 版本的参数。目标版本已有参数也会参与合并，不恢复其整套旧配置。

字段选择优先级：来源合法值 → 目标已有合法值 → 目标默认值。对象递归合并；数组整体选择。
`false`、`0`、空字符串、允许的 `null` 和空数组不会被当成未配置。
新增字段使用目标已有值或默认值；动态键只在目标 schema 明确禁止额外字段时省略。
类型、枚举、范围、字符串及数组约束不兼容时不猜测转换，逐字段回退，并保留其他合法字段。

安装和切换返回：

```json
{
  "config_valid": true,
  "config_migration_warnings": [
    {
      "path": "$.network.port",
      "source": "source",
      "reason": "$ must be <= 100",
      "action": "used_default"
    }
  ]
}
```

`source` 为 `source`、`target`、`default` 或 `result`；action 常见值为
`used_target`、`used_default`、`skipped`、`requires_configuration`。
warning 不导致迁移、安装或切换失败。缺少无合法来源/默认值的必填字段时，保留其他合法参数，
返回 `config_valid=false`，完成版本激活但不自动启动新版本；需补充配置后手动启动。
新安装包的 schema/default 仍需通过原有包校验，磁吸绑定的旧共享值若违反新约束则记为冲突，
不会覆盖合法迁移值或中断版本激活。

UI 在上传/覆盖安装完成及切换版本后显示 warning；安装事件流也记录字段与处理结果。
目标参数原子写入并保留配置乐观锁，来源版本参数保持不变；无变化时不增加配置修订号。

## 升级流程

`POST /aivuda_os/api/apps/{app_id}/upgrade` 上传新版本包：

1. 安装新版本（同 install 流程）
2. 自动激活新版本
3. 若 App 原先正在运行，自动重启

## update_this_version 脚本执行

`POST /aivuda_os/api/apps/{app_id}/update_this_version`

请求体：

```json
{
     "version": "1.2.3"
}
```

行为：

1. 校验 `version` 已安装
2. 读取该版本 manifest 的 `update_version` 字段（逻辑名称：`update_this_version`）
3. 若有脚本则执行；若无脚本则返回 `skipped=true`
4. 运行过程通过 SSE 事件流实时返回脚本输出

## Config-export import for bootstrap

Use the authenticated `POST /aivuda_os/api/config/import?token=<token>` with a
JSON body `{"document": <format_version 1 AivudaOS config export>,
"app_store_base_url": "http://127.0.0.1:<local-store-port>/"}`.
The local AppStore must serve both `/aivuda_app_store/store/.../download-url`
and the returned `/aivuda_app_store/files/...` URL. Poll
`GET /aivuda_os/api/apps/operations/{operation_id}?token=<token>` for phases,
result and failures. Missing app versions are installed through InstallerService;
existing versions are not overwritten. System/app parameters are merged and
validated through the existing config routes, then autostart is applied.
`human_header.avahi_hostname`, `payload.system_parameters.avahi_hostname` and
exported `running` state are ignored. No direct database import occurs.

## Popen stop and gateway exit

Popen applications are owned by the gateway instance that starts them. On
normal gateway shutdown that instance stops its owned apps; it does not stop
systemd-managed services or adopt another runtime's apps for shutdown. An
explicit app stop waits for cleanup, including observed descendants in other
sessions, before marking the app stopped. Processes get SIGTERM with a five
second grace period and then SIGKILL if necessary. Identity checks use Linux
PID start times. If cleanup fails, stop reports failure instead of recording a
successful stop. A detached guardian also cleans owned Popen apps when the
backend dies without running shutdown hooks. Autostart preferences are retained.

### 全局 app 环境变量

系统设置底部提供增删改表格，使用 `GET/PUT /api/config/os` 保存 `data.runtime_environment`。PUT 必须携带读取时的 `version`（冲突返回 409）。变量名必须匹配 `[A-Za-z_][A-Za-z0-9_]*` 且不能使用保留的 `AIVUDA_*`，值必须是无 NUL/换行的字符串。额外变量覆盖继承环境和默认日志变量，内部 app 路径变量保持由运行时管理。

Popen 和 systemd 的 start、restart、自启动 unit 生成均应用同一配置。保存后自动刷新持久化 systemd unit 并 daemon-reload，已运行进程在 app 下一次重启时获得新环境。响应包含 `runtime_environment_refresh_errors`，用于报告配置已保存但部分 unit 刷新失败。不会修改 AivudaOS 自身或安装/卸载 hook 的环境。删除变量后，Popen 恢复其父进程的继承值。

### Ubuntu APT 主源兼容

存在 `/etc/apt/sources.list.d/ubuntu.sources` 时编辑该文件并返回 `format: deb822`；否则编辑 `/etc/apt/sources.list` 并返回 `format: list`。前者是 Ubuntu 24.04 起默认布局，后者仍适用于旧系统或保留旧布局的升级安装。UI 显示实际目标路径和对应格式说明；deb822 更换镜像需编辑 `URIs` 并保留 Suites、Components、Signed-By 等字段。其他第三方源文件不会改变。

备份分别使用 `sources.list.<timestamp>.bak` 和 `ubuntu.sources.<timestamp>.bak`，列表仅包含当前目标的备份；旧 sources.list 备份 ID 仍受支持，跨源文件恢复返回 `BACKUP_TARGET_MISMATCH`。写入和恢复后照常执行 `apt update`。

## 在线商店更新提示

Online Store 导航图标右上角显示可更新的已安装 App 数量（超过 99 显示 99+，零时隐藏）。登录后检查商店索引，每 60 秒刷新；商店刷新及修改地址也同步更新。商店无法访问时清除角标，避免显示旧提示，不影响本机 App 使用。

商店卡片按 App ID 对照本机当前启用版本，显示“已安装 / 可更新 / 未安装”；商店版本高于本机时显示版本变化，并可通过“可更新（数量）”筛选。详情中的较新版本显示“更新”按钮，沿用现有下载安装及覆盖确认流程；安装成功重新读取本机版本，角标和标签随之更新，不自动安装。

版本比较按数字段及 SemVer 预发布规则进行，忽略构建元数据；未知格式或缺失版本不会触发更新提醒。当前商店索引没有设备兼容性字段，提示依据已发布版本，不额外推断设备兼容性。业务逻辑位于 `useStoreUpdates.js` 和 `services/core/storeUpdates.js`，中英文词条位于 `i18n/locales/`。

验证：在 aivudaOS 目录运行 `node --test tests/test_store_updates_ui.mjs`，在 UI 目录运行 `npm run build`。
