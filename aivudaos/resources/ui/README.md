# AivudaOS UI (Vue + Vite)

## 功能

- 登录页（用户名 + 密码）
- 登录后进入工作台：左侧可收起导航栏 + 右侧主显示区
- 左侧菜单：系统状态、应用菜单、在线应用商店（位于应用菜单下方）
- 系统状态：用户/角色、当前 AivudaOS 版本、网关连通性、应用统计（总数/运行中/自启动）
- 应用菜单：所有已安装 app 卡片（名称、版本、app_id、描述）
- 每个 app 卡片提供：启动开关、自启动开关（绿色/灰色）
- 应用菜单顶部提供批量操作：重启自启动应用、启动所有自启动应用、停止所有应用
- 应用详情页：输出日志、上传升级、切换版本、卸载（可选仅卸载当前版本/清理配置）
- 参数迁移提示：升级、切换（含降级）和覆盖安装尽量沿用来源参数；无法沿用的字段在安装弹窗/版本详情显示 warning，说明原因及采用目标值、默认值或省略；中英文支持。迁移提示使用完成结果，兼容 SSE 和轮询完成。
- 应用参数页：按版本编辑配置 JSON，查看 schema 与跨应用等值约束
- 在线应用商店：可设置 appstore 后端地址（保存在当前浏览器 localStorage），展示商店卡片、查看版本详情
- 商店版本操作：单按钮“下载并安装到 AivudaOS”，先触发浏览器原生下载到用户指定本机目录，再询问是否立刻安装
- 若选择立刻安装，会打开与“手动上传新应用安装包”相同的上传安装弹窗，选择刚下载文件后走同一安装流程
- 系统设置底部：额外 app 环境变量表格，支持增删改并保存，默认 `ROS_LOCALHOST_ONLY=1`；覆盖所有 app 的 Popen/systemd 启动，运行中的 app 重启后生效，unit 刷新失败会显示提示。
- APT 源编辑器：显示后端检测到的实际路径与 deb822/传统格式说明，兼容 `ubuntu.sources` 与 `sources.list`，按目标文件区分备份，恢复确认使用实际路径。
- 状态同步：操作后即时更新 + 后台轮询自动纠偏

## 参数弹窗复制

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
