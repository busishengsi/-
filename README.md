# AI 失物招领 Python 后端 工具链版

本版本在原有 Flask API 基础上加入操作系统与软件工程工具链，适合课程演示和答辩。Python 负责 HTTP 服务、认证、业务逻辑、SQLite 数据、文件上传、日志和维护命令；浏览器前端继续通过 `fetch` 调用 API。

## 一键运行

Windows 可双击 `start.bat`，也可以在 PowerShell 中执行：

```powershell
.\start.ps1
```

脚本会建立虚拟环境、安装依赖、检查文件目录和数据库，然后在 `http://127.0.0.1:5003` 启动服务。

## 手动工具链

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py init-db
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py system-info
.venv\Scripts\python.exe manage.py serve --port 5003
```

数据库在线备份：

```powershell
.venv\Scripts\python.exe manage.py backup
```

运行测试：

```powershell
.\run_tests.bat
```

## 前端交互

```javascript
const response = await fetch("http://127.0.0.1:5003/api/items");
const result = await response.json();
console.log(result.data.items);
```

需要登录的接口在请求头中携带令牌：

```javascript
headers: {
  Authorization: `Bearer ${localStorage.getItem("token")}`
}
```

主要接口包括注册登录、物品发布与搜索、图片上传与识别、认领审核和消息通知。`GET /health` 用于服务健康检查，`GET /api/system/status` 用于展示当前 Python 运行时、操作系统、进程、线程、磁盘和数据记录情况。

## 运行文件

运行数据统一放在 `instance` 目录：SQLite 数据库位于 `instance/lost_found.db`，上传文件位于 `instance/uploads`，滚动日志位于 `instance/logs/backend.log`，备份位于 `instance/backups`。可通过 `APP_DATA_DIR` 改变数据目录，通过 `APP_HOST`、`APP_PORT`、`APP_DEBUG` 和 `APP_LOG_LEVEL` 配置运行环境。

课程知识点与实现之间的对应关系见 `TOOLCHAIN_DESIGN.md`。
