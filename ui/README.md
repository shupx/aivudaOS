# AivudaOS UI (Vue + Vite)

## 功能

- 登录页（用户名 + 密码）
- 登录后进入工作台：左侧可收起导航栏 + 右侧主显示区
- 左侧菜单：系统状态、应用菜单
- 系统状态：用户/角色、网关连通性、应用统计（总数/运行中/自启动）
- 应用菜单：所有已安装 app 卡片（名称、版本、app_id、描述）
- 每个 app 卡片提供：启动开关、自启动开关（绿色/灰色）
- 应用详情页：输出日志、上传升级、切换版本、卸载（可选仅卸载当前版本/清理配置）
- 状态同步：操作后即时更新 + 后台轮询自动纠偏

## 目录结构

- `src/state/`：全局响应式状态
- `src/services/core/`：API 与业务服务
- `src/composables/`：页面/模块业务逻辑
- `src/components/apps/`：应用卡片与开关组件
- `src/views/`：页面视图（无重业务逻辑）

## 启动

```bash
npm install
npm run dev
```

开发环境后端地址由 `vite.config.js` 的 `/api` 代理决定（当前指向 `http://127.0.0.1:8000`）。

## 打包

```bash
npm run build
npm run preview
```
