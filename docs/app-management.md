# AivudaOS App 管理

## 概述

AivudaOS 通过 **本地上传安装包** 的方式管理应用。每个 App 以 `.tar.gz`、`.tgz`、`.tar`、`.tar.xz`、`.txz` 或 `.zip` 压缩包上传，包内必须包含 `manifest.yaml` 描述文件。系统支持多版本共存、版本切换、进程生命周期管理和自启动。

当前 UI 还支持“在线应用商店”入口：从 aivudaAppStore 或另一台 aivudaOS 的共享地址查看应用与版本，先下载安装包到浏览器本机，再一键上传到 AivudaOS 安装。

当前 UI 新增“配置参数”中心入口（Dashboard 侧边栏），统一管理所有已安装 app 的 **active 版本** 配置。各 app 详情页仅保留跳转到统一参数中心，不再提供分散编辑入口。

前端 UI 支持 `zh-CN / en-US` 语言切换（Dashboard 左侧栏入口），并将选择持久化到本地存储。当前版本只对前端固定文案做国际化，后端返回的动态文本（如 SSE 日志、错误详情）按原文显示。

App 的 `start / stop / restart` 与批量 `restart-running / restart-autostart / start-autostart / stop-all` 现在会先返回 queued operation，由后台线程并行执行；同一 app 仍然保留单操作冲突保护。

默认流水线没有配置分组时，列表顶部的三个操作分别重启当前运行的 App、启动设为自启的 App、停止所有 App。配置了分组后，这三个位置控制默认流水线，作用范围限于方案里启用的组和节点，切回平铺显示也遵循此规则。

## 启动流水线

应用列表读取 `default_profile`。默认方案含非空分组时，列表按阶段显示分组框，未分组应用放在底部。组标题显示执行模式和运行数。使用标题右侧按钮启动、重启或停止单组，使用列表工具栏操作整条流程。执行中可取消。搜索仍可跳转到卡片，切换平铺或紧凑布局后也可使用。

在 Apps 顶部切换到「启动流水线」，新建分组并展开未分组托盘。点击 App 可加入首组，也可以拖入目标分组。托盘和画布的 App 卡片均为 200 × 76。应用列表的标准卡片宽 300 px，紧凑模式宽 240 px，窄屏按可用空间收缩。

在两组之间，从上游组框右侧的圆点拖到下游组框左侧的圆点。选中连线后按 Delete 或 Backspace 可断开。可以保留多个独立分组、分支和汇合。移动组框只改变位置。App 之间也可用同样的方式创建就绪依赖，包括从画布右侧连向左侧。串行组内的顺序箭头随组内次序和 App 依赖自动生成。

双击组名可重命名。「自动整理」重新排列卡片。拖动结束或修改连线后，编辑器等待 500 ms 自动保存。设置中可切换方案、选择失败策略和开机接管，或应用 ROS 2 分组模板。

每组的 `depends_on` 保存前置组 ID，每个 App 的 `depends_on` 保存前置 App ID。新建组的前置组为空。读取整份未声明组依赖的旧方案时，系统按旧的 `order` 将启用组串接，首次保存时写入这些显式连线。停用或空的中间组在调度时传递其上游约束。最后一个版本卸载后，系统清理各方案的节点、布局和引用。

并行组中的节点在自身前置条件满足后即可提交，全方案最多同时执行 8 个任务。串行组按拓扑次序逐个执行。组间依赖要求上游组启用的成员就绪。只需等待某个 App 时可仅连接 App。单组启动默认检查外部前置条件。画布的「连带启动上游依赖」按钮和列表的「连带启动上游」选项可补启缺少的前置 App。单组重启会先检查上游，预检失败时保留整组运行状态。

`abort` 在观察到失败后停止提交后续节点。`skip_dependents` 跳过失败项的后继并继续运行独立分支。`continue` 尝试启动后继并将受影响的节点标为降级。停止按实际依赖逆序执行，停止失败会阻止提交剩余任务。取消会中断探活和后续调度，已运行的进程继续运行。列表和画布均可查看运行日志及探活失败原因。

旧版后端拒绝分组的 `depends_on` 字段时，编辑器保留草稿并提示更新当前网关。若使用 ACEswarm，本机页面和无人机页面各有独立后端，分别部署和验证。

### 配置和开机行为

`${AIVUDAOS_WS_ROOT:-$HOME/aivudaOS_ws}/config/startup_pipeline.yaml` 首次保存时生成。不存在时返回版本 `0` 和空的 `default` profile。以下片段可用于有 `driver`、`localizer` 两个已安装 App 的设备（API 接收对应的 JSON）：

```yaml
version: 0
takeover_autostart: false
default_profile: robot
profiles:
  - name: robot
    on_failure: skip_dependents
    groups:
      - id: hardware
        depends_on: []
        name: Hardware & Drivers
        order: 0
        mode: parallel
        enabled: true
        items:
          - app_id: driver
            readiness: {type: ros2_topic, topic: /scan, require_message: true, timeout_sec: 30}
      - id: localization
        depends_on: []
        name: Localization
        order: 1
        items:
          - app_id: localizer
            depends_on: [driver]
            readiness: {type: ros2_lifecycle, node_name: /localizer, lifecycle_state: active}
```

可选的 `profile.layout` 保存显示位置。例如 `{"group:hardware":{"x":20,"y":30},"app:driver":{"x":24,"y":64}}`。分组使用画布坐标，App 使用相对于分组左上角的坐标。每项须有有限数值 `x`、`y`，可选宽高 `w`、`h` 须为正的有限数值。省略布局时按执行顺序自动排布。启停计划始终由 `groups`、`items` 与 `depends_on` 决定。

接管默认关闭：Popen 继续重放原有 `autostart`，systemd 继续管理独立 unit。**只有保存接管开关才改变开机行为**：在 systemd 模式下，保存时立即禁用已安装 App 的独立 unit 自启，不停止已运行进程；网关启动时再校正并运行默认 profile。接管期间保留单 App 自启偏好，关闭接管并保存后恢复，不自动启动此前未运行的 App。接管开启但计划无启用节点时不会启动任何 App。

### 就绪探活

| `type` | 放行条件 |
|---|---|
| `started`（默认） | 启动后确认进程仍在运行 |
| `delay` | 存活满 `delay_sec`（默认 1 秒） |
| `tcp` | 本机 `host:port` 可连接，host 限 `localhost` 或回环 IP，默认 `127.0.0.1` |
| `http` | GET `url` 收到 HTTP 2xx；不跟随重定向 |
| `log_contains` / `log_regex` | 本次启动的 `current.log` 中出现指定的 `pattern`。两种后端在启动新进程时清空日志，增量匹配保留上一块末尾 64 KiB |
| `exited_zero` | 运行后端记录到退出码 0，可用于一次性脚本。非零退出或信号终止会报告失败 |
| `ros2_node` | 发现完整名称与 `node_name` 相同的节点 |
| `ros2_topic` | 发现 `topic`。勾选 `require_publisher` 检查发布者数量。勾选 `require_message` 后，必须在探活期间实际收到一条消息 |
| `ros2_lifecycle` | 节点的 GetState 服务返回目标 `lifecycle_state`，默认 `active` |
| `command` | 应用安装目录中的 shell 命令 `command` 成功退出 |

`timeout_sec` 默认 30 秒，`interval_sec` 默认 1 秒。流水线按运行域及中间件环境复用短生命周期的 rclpy 子进程，结束后回收。ROS 探活使用 App 的有效域与运行环境。若网关 PATH 中缺少 ros2，但可在 `/opt/ros` 中唯一确定发行版，探针会加载该发行版的 setup.bash。自定义消息需要在探针运行环境提供对应的消息包及类型支持。首帧探活使用 best-effort、volatile 订阅。命令探活以网关账号运行，仅填写可以重试的探测命令。

### HTTP 与事件

以下路径相对 `/aivuda_os/api/apps`，均需 `token` 查询参数：

| 方法与路径 | 用途 |
|---|---|
| `GET /pipeline` | 返回 `config`、`installed_apps`、默认 profile 的 `unassigned_apps`、`validation`（含各 profile 的分组批次预览）和 `active_operation` |
| `POST /pipeline/validate` | 请求体为完整草稿；只返回 `{valid, errors, preview}`，不改变文件或运行状态 |
| `PUT /pipeline` | 请求体为完整配置，携带最近读取的 `version`。成功后原子替换并返回新版本；旧版本返回 409，无效配置返回 422 |
| `POST /pipeline/run` | 空请求体运行默认 profile；`{"profile":"robot","group_id":"hardware"}` 只运行指定组；添加 `"with_deps": true` 可启动未运行的前置项 |
| `POST /pipeline/stop` | 逆序停止整条方案，也可传 `group_id` 仅停止一组。若组外下游节点仍在运行，事件流会给出英文提示 |
| `POST /pipeline/restart` | 请求体同 `run`。在同一操作及同一套 App 锁内先逆序停止，停止全部成功后按依赖启动并执行就绪探活 |
| `GET /pipeline?view=list` | 应用列表轻量读取 `config` 和 `active_operation`，实时安装清单由已有列表接口提供 |

启动、停止和重启均返回 202 和 `operation_id`。`GET /operations/{operation_id}/events` 可从头回放 `pipeline_stage`、`pipeline_node`、`log` 及终态事件；节点状态与实际进程状态独立。在应用列表与流水线编辑器间切换时，页面继续订阅同一个操作，两个标签共用进度和日志。`POST /operations/{operation_id}/cancel` 请求取消。运行中的流水线会占用所涉及 App 的 operation 名额，冲突返回 409。同一网关只允许一条流水线操作同时执行，操作记录与 SSE 回放仅保存在该网关进程内。

MCP 提供 `get_startup_pipeline`、`run_startup_pipeline`、`restart_startup_pipeline` 和 `stop_startup_pipeline`。内置 HTTP MCP 的流水线接口要求调用方显式提供 session token，见 [MCP 认证说明](mcp.md#认证与请求隔离)。

### 参数值输入历史

配置参数中心的应用、系统、磁吸文本/数字输入框提供可选择的历史值。点击输入框显示该参数最近的历史记录，输入时过滤，支持鼠标点击或方向键与回车选择；选择后仍走原有类型校验和提交流程。失焦/回车成功提交后缓存，失败值不记录。

历史保存在浏览器 localStorage，按站点、范围、App ID、参数路径和类型隔离，每个参数最多 20 个不同值，刷新页面后保留。只读及密码/密钥类字段不缓存；布尔、枚举、数组/对象编辑器不变。存储不可用不影响编辑和保存。实现位于 `services/core/parameterValueHistory.js`、`composables/useParameterValueInput.js` 和 `components/app-config-center/ParameterValueInput.vue`。验证：`node --test tests/test_parameter_value_history.mjs`，UI 构建：`npm run build`。

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
- 网关为应用的 `/<app>/ui/*` 和 `/<app>/api/*` 默认返回 `Cache-Control: no-store`。应用路由未注册时，这些地址返回 404；工作台的深层链接仍可打开首页。旧网关留下的浏览器缓存可通过清除对应站点的页面缓存移除。
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

覆盖安装（同版本 `overwrite=true`）时，安装器暂存旧目录，在最终版本路径执行 `pre_install`，成功发布后才丢弃备份。安装中途报错或取消会撤销本次安装对版本目录、安装记录、活动链接和受管配置的修改；若已尝试更新 Caddy，则按恢复后的活动版本重新生成路由并尝试重载。这不是断电恢复机制，安装脚本自行修改的操作系统文件或外部服务也不在回滚范围内。覆盖运行中的版本前建议先停止应用；安装操作结束前不要同时切换或卸载这个应用。


## 文件系统布局
默认运行时根目录：`$HOME/aivudaOS_ws`（可通过环境变量 `AIVUDAOS_WS_ROOT` 覆盖）。

配置说明：

- `config/os.yaml`：系统运行参数（如 `runtime_process_manager`、`runtime_systemd_scope`、`avahi_hostname`），不参与磁吸。
- ROS 2 主机在系统设置中只读汇总全局默认值和应用实际声明的 Domain 参数。点击「前往配置参数修改」可在配置中心的「ROS 2 通信域参数」中保存全局值或应用字段。每个算法的 Domain 参数独立管理，不参与磁吸同步。应用下次启动时使用新的配置。
- 新安装包建议在各自算法命名空间下声明 `ros_domain_id` 或 `domain_id`（例如 `camera.ros_domain_id`、`apriltag.ros_domain_id`、`policy.ros_domain_id`、`fastlio.ros_domain_id`、`zenoh.ros_domain_id`），默认 `-1` 表示继承全局 `sys.ros2_default_domain_id`，`0~232` 为独立覆盖。自定义字段可在 JSON Schema 中添加 `"x-ros-domain": true`，或在标题、说明中指明 `ROS_DOMAIN_ID`。页面读取激活版本的 schema、默认配置和当前配置，显示原字段路径。未声明 Domain 的应用不会生成占位行。
- 对没有 ROS/DDS 语义的字符串字段，仅凭 `domain_id` 后缀不会把 UUID 等文本改成数字编辑器。数组内声明 Domain 时，磁吸不会复制整个数组；编辑某个元素的 Domain 不应覆盖其他元素。声明为字符串（含可空字符串）的 Domain 仍以 JSON 字符串保存。
- 升级时，全局 Domain 按 `sys.ros2_default_domain_id`、`os.yaml` 的 `runtime_environment.ROS_DOMAIN_ID`、服务环境变量的顺序取第一个合法值。有效旧数字字符串会转成整数；没有合法来源时使用 `0`。
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

### 日志读取

`GET /api/apps/{app_id}/logs?from_end=true` 只返回当前文件末尾的位置（`next_offset`），`chunk` 为空，不读取或截断日志内容。需要从此刻开始跟随输出时，在下次请求中把该值作为 `offset`。若获取末尾位置失败，继续使用上一次成功读取的偏移，以免漏掉断线期间的输出。

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

1. 在 UI 的“在线应用商店”页面设置商店地址（默认 `http://127.0.0.1:28791`；自定义地址保存到浏览器 localStorage，key: `aivuda_ui_appstore_base_url`）。
2. 前端调用：`{appstore_base_url}/aivuda_app_store/store/index` 获取应用卡片列表。
3. 点击应用后调用：`.../store/apps/{app_id}` 查看版本详情。
4. 点击“下载到本机”后，前端调用 `.../download-url` 与 `.../download`，将安装包下载到浏览器本机。
5. 点击“安装到 AivudaOS”后，前端把该下载文件通过 `POST /aivuda_os/api/apps/upload` 上传给本机 AivudaOS，安装流程与手动上传一致。

### 从另一台 aivudaOS 安装应用

1. 从浏览器用局域网地址打开来源设备（例如 `http://192.168.20.21`），登录后进入「在线应用商店」，点击「共享本机已安装应用」并复制共享地址。
2. 登录目标设备（例如 `http://192.168.20.20`），在同一页面的商店地址栏粘贴完整共享地址，点击「提交」。浏览器必须能访问两台设备。通过 HTTPS 打开目标页面时，来源设备也应使用浏览器信任的 HTTPS 地址。
3. 打开应用，选定版本，点击「下载并安装到 AivudaOS」。大小不超过 200 MiB 时，浏览器直接把包上传到目标设备；更大的包先下载到本机，再由用户选择文件上传。

共享地址由来源设备上已登录的用户生成，持有者可在一小时内读取全部已安装应用及其版本，重新生成即使旧地址失效。无需部署独立商店或重新上传已有版本。下载包是所选安装目录的 tar 快照，含应用文件、包内默认配置及安装时生成的文件。安装目录中的本机文件也会随包传输。单独存储的系统配置、运行数据和日志在安装目录之外。打包保留目录内有效的相对符号链接，跳过绝对链接、指向目录外的链接和特殊文件。目标设备仍需满足应用的架构与依赖要求，安装时会照常执行安装钩子。

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

新包若将旧域号迁至 `<section>.ros_domain_id`，可在 schema 根节点声明 `x-ros-domain-migration: {section: camera}`。升级时先按旧配置解析生效值，再移除 `ros.domain_id` 并合并默认值。新旧值同时存在时保留新值（含 -1）。QRLand 的旧启动器在新值为 -1 时优先采用已有旧值，因此其迁移声明额外设置 `legacy_when_inheriting: true`。

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
exported `running` state are ignored. `payload.system_parameters` is optional: omit it for an app-only import. If a systemd unit cannot be refreshed, the saved system setting is retained, other apps are processed, and `result.runtime_environment_refresh_errors` identifies the affected units. No direct database import occurs.

## Popen stop and gateway exit

Popen applications are owned by the gateway instance that starts them. On
normal gateway shutdown that instance stops its owned apps; it does not stop
systemd-managed services or adopt another runtime's apps for shutdown. An
explicit app stop waits for cleanup, including observed descendants in other
sessions, before marking the app stopped. Processes get SIGTERM with a five
second grace period and then SIGKILL if necessary. Identity checks use Linux
PID start times. Repeated starts in the same gateway reuse the running instance without truncating its log. For explicit stop after a gateway restart, the recorded PID, Linux boot ID and process start time must still match. Legacy PID-only rows cannot prove ownership: stop Popen apps before upgrading; if an old process survived an abnormal shutdown, verify it manually before starting another instance. Systemd-managed apps continue to use unit state. If cleanup fails, stop reports failure instead of recording a
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

### 设备网卡和源地址选项

应用可在顶层配置组的 schema 声明 `x-device-ipv4: {interface: host_interface, address: host_ip, destination: ip}`，值为同组字段名。接口和源地址字段均使用字符串，`auto` 表示按当前目标的直连 IPv4 路由选择。除了以太网，具有 IPv4 地址的非回环接口（如 `wg0`）也可选择；自动模式仍要求链路已启用、内核路由无网关且源地址属于该接口。同一请求复用网卡快照，网络探测不占用网关事件循环。

从应用参数或磁吸区切换接口或目的地址时，只将实际受影响应用的可编辑源地址恢复为 `auto`。源地址本身已绑定磁吸时，由该绑定决定其值。只打开页面或重算未变化的绑定不会清除手动源地址。

若安装钩子为旧客户端生成静态 enum，在相应字段声明 `x-device-choice: interface` 或 `address` 可同时接受后来添加的接口或地址。已保存的选择即使暂时离线，也不因缺席当前网卡列表而阻止修改其他字段或通过启动前的配置校验。新选择仍需满足校验；实际使用网络时，应用须重新核对网卡、链路和地址。
