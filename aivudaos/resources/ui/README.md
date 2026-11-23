# AivudaOS UI (Vue + Vite)

## 功能

- 登录页（用户名 + 密码）
- 登录后进入工作台：左侧可收起导航栏 + 右侧主显示区
- 左侧菜单：系统状态、应用菜单、在线应用商店（位于应用菜单下方）
- 系统状态：用户/角色、当前 AivudaOS 版本、网关连通性、应用统计（总数/运行中/自启动）
- 应用菜单：所有已安装 app 卡片（名称、版本、app_id、描述）
- 每个 app 卡片提供：启动开关、自启动开关（绿色/灰色）
- 应用菜单顶部提供批量操作：重启所有正在运行的应用（不受自启动开关影响）、启动所有自启动应用、停止所有应用
- 应用详情页：输出日志、上传升级、切换版本、卸载（可选仅卸载当前版本/清理配置）
- 参数迁移提示：升级、切换（含降级）和覆盖安装尽量沿用来源参数；无法沿用的字段在安装弹窗/版本详情显示 warning，说明原因及采用目标值、默认值或省略；中英文支持。迁移提示使用完成结果，兼容 SSE 和轮询完成。
- 应用参数页：按版本编辑配置 JSON，查看 schema 与跨应用等值约束
- 配置参数中心：应用、系统和磁吸的文本/数字值输入框提供历史下拉选项，可点击或用方向键、回车选择；成功提交后在当前浏览器按参数保存最近 20 个不同值，刷新后仍保留。只读、密码/密钥类字段不缓存，布尔、枚举及数组/对象编辑器沿用原交互。
- 在线应用商店：默认地址为 `http://127.0.0.1:28791`，可设置 appstore 后端地址（保存在当前浏览器 localStorage），展示商店卡片、查看版本详情
- 设备间分享：来源设备在商店页点击「共享本机已安装应用」，将共享地址粘贴到目标设备的商店地址栏，可按版本下载并安装。
- 商店版本操作：小于等于 200 MiB 的包直接交给上传安装弹窗，更大的包先下载再选择文件安装。
- 若选择立刻安装，会打开与“手动上传新应用安装包”相同的上传安装弹窗，选择刚下载文件后走同一安装流程
- 系统设置底部：额外 app 环境变量表格，支持增删改并保存，默认 `ROS_LOCALHOST_ONLY=1`；覆盖所有 app 的 Popen/systemd 启动，运行中的 app 重启后生效，unit 刷新失败会显示提示。
- APT 源编辑器：显示后端检测到的实际路径与 deb822/传统格式说明，兼容 `ubuntu.sources` 与 `sources.list`，按目标文件区分备份，恢复确认使用实际路径。
- 状态同步：操作后即时更新 + 后台轮询自动纠偏

## 启动流水线

打开「启动流水线」后才加载 `@vue-flow/core` 及其样式。新建分组，展开未分组托盘，点击 App 加入首组，或拖入目标分组。将上游 App 的右锚点连到下游 App 的左锚点即可添加依赖。选中依赖线并按 Delete 或 Backspace 删除。双击组名可重命名，点组内的 ▶ 可单独启动该组，点 App 可编辑就绪探活。设置中可切换 profile、应用 ROS 2 分层模板、设置失败策略和开机自启。

`src/services/core/pipelineGraph.js` 将执行模型投影为画布，也校验连线和移动。`usePipelineCanvas.js` 用 `shallowRef` 保存节点与边，按节点索引更新相邻边动画。`useStartupPipeline.js` 管理编辑和运行，`usePipelineAutosave.js` 在松手或连线变更后等待 500 ms 再提交，同一时间只发送一个 PUT。版本冲突会保留本地草稿，确认重新加载后才读取服务器版本。自动整理仅更新当前 profile 的布局。

逻辑验证：在仓库根目录运行 `node --test tests/test_startup_pipeline_ui.mjs`，在本目录运行 `npm run build`。后端规则见[应用管理](../../../docs/app-management.md#启动流水线)。

## 参数弹窗复制

参数值历史由 `services/core/parameterValueHistory.js` 和 `useParameterValueInput.js` 管理，`ParameterValueInput.vue` 复用现有输入样式及失焦/回车提交逻辑。localStorage 按站点、参数范围、App ID、参数路径及类型隔离；历史选择同样经过原有校验及保存。存储不可用时仍可编辑和提交。验证：`node --test tests/test_parameter_value_history.mjs`（从 aivudaOS 根目录运行）。

参数中心的默认值弹窗及数组/对象编辑弹窗共用 `src/services/core/clipboard.js`：优先使用 Clipboard API，在 API 缺失（非安全 HTTP）或被 Electron WebView 权限拒绝时，降级为文本选区复制；失败显示国际化提示。默认值弹窗逻辑位于 `src/composables/useDefaultValueModal.js`。


参数表列宽及拖拽分隔线统一由 `useResizableConfigTable` 管理；列位置未变化时不写响应式状态，避免 `onUpdated → requestAnimationFrame → 新数组 → onUpdated` 的空闲刷新循环。表格异步出现后自动绑定滚动和尺寸监听，离开页面时清理。回归验证：`node --test tests/test_config_table_layout.mjs`（需先安装 UI 依赖）。

## 目录结构

- `src/state/`：全局响应式状态
- `src/services/core/`：API 与业务服务
- `src/composables/`：页面/模块业务逻辑（包含 apps 页批量控制）
- `src/components/apps/`：应用卡片与开关组件
- `src/views/`：页面视图（无重业务逻辑）

## 启动

```bash
npm install
npm run dev
```

开发环境后端地址由 `vite.config.js` 的 `/aivuda_os/api` 代理决定（当前指向 `http://127.0.0.1:8000`）。

后端同时内置 `/aivuda_os/mcp`，生产 Caddy 的 HTTP/HTTPS 入口会将该路径代理到
同一后端，不会回退为 UI 静态页面。MCP 客户端使用后端或 Caddy 入口，见
[MCP 使用说明](../../../../docs/mcp.md)；浏览器 UI 登录不会自动认证 MCP 请求。

## 打包

```bash
npm run build
npm run preview
```

前端构建产物会输出到当前目录下的 `dist/`，也就是仓库中的 `aivudaos/resources/ui/dist`，供后端/Caddy 和 wheel 打包统一复用。

迁移提示逻辑测试（从仓库根目录运行）：

```bash
node --test tests/test_config_migration_ui.mjs
```

## 在线商店更新提示

Online Store 导航图标右上角显示可更新的已安装 App 数量（超过 99 显示 99+，零时隐藏）。登录后检查商店索引，每 60 秒刷新；商店刷新及修改地址也同步更新。商店无法访问时清除角标，避免显示旧提示，不影响本机 App 使用。

商店卡片按 App ID 对照本机当前启用版本，显示“已安装 / 可更新 / 未安装”；商店版本高于本机时显示版本变化，并可通过“可更新（数量）”筛选。详情中的较新版本显示“更新”按钮，沿用现有下载安装及覆盖确认流程；安装成功重新读取本机版本，角标和标签随之更新，不自动安装。

版本比较按数字段及 SemVer 预发布规则进行，忽略构建元数据；未知格式或缺失版本不会触发更新提醒。当前商店索引没有设备兼容性字段，提示依据已发布版本，不额外推断设备兼容性。业务逻辑位于 `useStoreUpdates.js` 和 `services/core/storeUpdates.js`，中英文词条位于 `i18n/locales/`。

验证：在 aivudaOS 目录运行 `node --test tests/test_store_updates_ui.mjs`，在 UI 目录运行 `npm run build`。

## ROS 2 系统参数

系统设置仅在服务端识别到 ROS 2 时显示 Domain ID。系统设置显示只读摘要，可直接跳转到配置中心的「ROS 2 通信域参数」区编辑全局值和应用声明的 Domain 字段。没有保存配置时，包内提供的域值显示为默认值；域在数组中时，父级只读绑定同样生效。非 ROS 的文本标识（例如身份提供方 UUID）仍使用普通文本编辑器。

免密 sudo 开关以服务端确认的状态为准：密码错误或取消时保留旧状态，保存成功后更新开关并关闭弹窗。浏览器回归使用模拟 API，不修改真实 sudo 设置；在 ACEswarm 开发环境构建 UI 后，从 aivudaOS 根目录运行 `node --test tests/browser/test_sudo_settings.mjs`（使用已安装的 Chrome 可设 `PLAYWRIGHT_CHANNEL=chrome`）。

## 导入与日志恢复

- 全局 Domain 配置已保存、但有 systemd unit 刷新失败时，导入结果会显示失败详情。先修正相应应用的配置或写入权限，再刷新 unit；无需重复导入已经写入的应用参数。
- 应用详情的「清空显示」只向服务端请求末尾偏移，不下载历史日志，也不删除文件。若获取偏移失败，下一次轮询从上次已知的偏移恢复，而不是跳过断线期间的输出。构建 UI 后可运行 `node --test tests/browser/test_app_log_recovery.mjs` 验证。

## 设备网卡配置

声明 `x-device-ipv4` 的配置组可以选择网卡和源 IPv4。通过普通参数或磁吸区更换网卡、目的地址时，对应的可编辑源地址会恢复为 `auto`，由其他磁吸组管理的源地址保留原值。已保存的离线选项不妨碍修改其他参数；配置可保存不代表网络当前可用。

## 机载应用入口

IMX219 与 AprilTag 的参数在应用参数中心管理。图传从地面站 Foxglove 的 Image 面板打开；C20D 保留自己的云台控制面板。操作步骤见[机载联调说明](../../../docs/drone-camera-gimbal.md)。
