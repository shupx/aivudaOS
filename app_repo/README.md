# app_repo

远端应用仓库服务（可上传、更新、下架）。

## 启动

```bash
python3 -m pip install --user -r app_repo/requirements.txt
python3 -m uvicorn app_repo.main:app --host 0.0.0.0 --port 9001
```

## 关键接口

- `GET /repo/index` 应用商店目录（仅 `listed`）
- `POST /repo/apps/upload` 上传或更新应用版本（multipart）
- `POST /repo/apps/{app_id}/delist` 下架应用
- `POST /repo/apps/{app_id}/list` 重新上架
- `DELETE /repo/apps/{app_id}/versions/{version}` 删除版本
- `GET /repo/admin/apps` 管理端列表

## 上传示例

```bash
curl -X POST http://127.0.0.1:9001/repo/apps/upload \
  -F app_id=serial-tool \
  -F version=2.2.0 \
  -F name='Serial Tool' \
  -F runtime=host \
  -F run_entrypoint='./serial-tool' \
  -F run_args_json='["--device","/dev/ttyUSB0"]' \
  -F config_schema_json='{"type":"object","properties":{"device":{"type":"string"},"baudrate":{"type":"integer"}}}' \
  -F default_config_json='{"device":"/dev/ttyUSB0","baudrate":115200}' \
  -F file=@/path/to/serial-tool.tar.gz
```
