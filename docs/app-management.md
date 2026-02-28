# AivudaOS App 管理

## 概述

AivudaOS 通过 **本地上传安装包** 的方式管理应用。每个 App 以 `.tar.gz` 或 `.zip` 压缩包上传，包内必须包含 `manifest.yaml` 描述文件。系统支持多版本共存、版本切换、进程生命周期管理和 systemd 自启动。

## 核心模块

| 模块 | 路径 | 职责 |
|---|---|---|
| InstallerService | `core/apps/installer.py` | 解压安装包、解析 manifest、写入文件和数据库 |
| VersioningService | `core/apps/versioning.py` | 多版本目录管理、symlink 切换 |
| RuntimeService | `core/apps/runtime.py` | 启动/停止/重启、autostart、卸载 |
| ConfigService | `core/config/service.py` | 每个 App 的 YAML 配置读写 |

依赖注入在 `gateway/deps.py`，API 路由在 `gateway/routes/apps.py`。

## 安装包格式

```
my-app-1.0.0.tar.gz
├── manifest.yaml        # 必须
├── start.sh             # 入口脚本
└── ...                  # 其他应用文件
```

> 支持包内有一层包裹目录（如 `my-app/manifest.yaml`），系统会自动向下查找。

### manifest.yaml 字段

```yaml
app_id: my-app                 # 唯一标识（必填）
name: My App                   # 显示名称
version: 1.0.0                 # 版本号（必填）
description: 一个示例应用
run:
  entrypoint: ./start.sh       # 启动入口（必填）
  args: []                     # 启动参数
default_config: {}             # 默认配置，安装时写入 config/apps/{app_id}.yaml
config_schema: null            # 配置校验 schema（可选）
```

## 文件系统布局

```
aivudaOS/
├── apps/                          # 所有 App 安装目录
│   └── {app_id}/
│       ├── versions/
│       │   ├── 1.0.0/            # 版本目录（实际文件）
│       │   └── 1.1.0/
│       └── active -> versions/1.1.0   # symlink 指向当前激活版本
├── config/
│   └── apps/
│       └── {app_id}.yaml         # 每个 App 的运行配置
├── data/
│   ├── aivuda.db                 # SQLite 数据库
│   └── uploads/                  # 上传临时目录
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
  创建版本目录 apps/{app_id}/versions/{version}/
       │
       ▼
  复制所有文件到版本目录
       │
       ▼
  写入 app_installation 表 + app_runtime 表
       │
       ▼
  初始化 config/apps/{app_id}.yaml
       │
       ▼
  创建 symlink: apps/{app_id}/active → versions/{version}
```

## 运行时管理

- **启动**：根据 `manifest.run.entrypoint` 构建命令，`subprocess.Popen` 启动（`start_new_session=True`）
- **停止**：`os.kill(pid, SIGTERM)`
- PID 记录在 `app_runtime` 表

### 自启动（Autostart）

通过 systemd user service 实现：
- 自动生成 `~/.config/systemd/user/aivuda-app-{app_id}.service`
- `systemctl --user enable/disable` 控制

## API 端点

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/api/apps/upload` | 上传安装包（首次安装） |
| POST | `/api/apps/{app_id}/upgrade` | 上传新版本（升级，若正在运行则自动重启） |
| GET | `/api/apps/installed` | 已安装应用列表 |
| GET | `/api/apps/{app_id}/status` | 应用详情（安装信息 + 运行状态） |
| POST | `/api/apps/{app_id}/start` | 启动 |
| POST | `/api/apps/{app_id}/stop` | 停止 |
| POST | `/api/apps/{app_id}/restart` | 重启 |
| POST | `/api/apps/{app_id}/autostart` | 设置自启动 `{ "enabled": true }` |
| GET | `/api/apps/{app_id}/versions` | 版本列表 |
| POST | `/api/apps/{app_id}/switch-version` | 切换版本 `{ "version": "1.0.0", "restart": true }` |
| POST | `/api/apps/{app_id}/uninstall` | 卸载 `{ "purge": false, "version": null }` |
| GET | `/api/apps/{app_id}/config` | 获取 App 配置 |
| PUT | `/api/apps/{app_id}/config` | 更新 App 配置 `{ "version": 1, "data": {...} }` |

> 所有端点需要 `token` 参数进行身份验证。

## 版本管理

- 同一 App 可安装多个版本，共存于 `apps/{app_id}/versions/` 下
- `active` symlink 指向当前激活版本
- `switch-version` 可切换激活版本，可选自动重启
- `uninstall` 可删除单个版本或整个 App（`purge=true` 同时删除配置）

## 升级流程

`POST /api/apps/{app_id}/upgrade` 上传新版本包：

1. 安装新版本（同 install 流程）
2. 自动激活新版本
3. 若 App 原先正在运行，自动重启
