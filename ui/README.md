# AivudaOS UI (Vue + Vite)

## 功能

- 登录页（后端地址 + 用户名 + 密码）
- 登录后进入工作台：左侧可收起导航栏 + 右侧主显示区
- 左侧菜单：系统状态、应用菜单
- 系统状态：用户/角色、网关连通性、应用统计（总数/运行中/自启动）
- 应用菜单：所有已安装 app 卡片（名称、版本、app_id、描述）
- 每个 app 卡片提供：启动开关、自启动开关（绿色/灰色）
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

默认后端地址：`http://127.0.0.1:8000`（可在登录页修改并持久化）。

## 打包

```bash
npm run build
npm run preview
```
