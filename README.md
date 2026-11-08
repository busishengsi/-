# AI 失物招领前后端整合版

本版本将最新的 6 个 HTML 页面与 Python Flask 后端整合为一个可直接运行的项目。Python 同时提供前端页面和 API，负责认证、发布审核、物品列表、详情、AI 图片识别、认领流程、SQLite 数据、上传、日志和维护命令。

## 一键运行

Windows 可双击 `start.bat`，也可以在 PowerShell 中执行：

```powershell
.\start.ps1
```

脚本会建立虚拟环境、安装依赖、检查文件目录和数据库，然后在 `http://127.0.0.1:5000` 启动服务。不要再双击打开 HTML 文件，应始终通过这个地址访问。

## 首次建立审核管理员

打开 PowerShell，在项目目录执行：

```powershell
.venv\Scripts\python.exe manage.py create-admin admin admin123
```

随后使用 `admin` 和 `admin123` 登录，即可进入审核管理页。正式演示前建议将示例密码替换为自己的密码。

## 手动工具链

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py init-db
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py system-info
.venv\Scripts\python.exe manage.py serve --port 5000
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
const response = await fetch("/api/items");
const result = await response.json();
console.log(result.data.items);
```

需要登录的接口在请求头中携带令牌：

```javascript
headers: {
  Authorization: `Bearer ${localStorage.getItem("token")}`
}
```

发布的信息默认进入待审核状态，普通列表只显示审核通过的信息。管理员通过 `GET /api/admin/items` 查看审核队列，通过 `PATCH /api/admin/items/<id>/audit` 执行通过或驳回。审核状态与物品的开放、已认领、已关闭状态彼此独立。

主要接口还包括注册登录、物品搜索、图片上传与识别、认领申请和消息通知。`GET /health` 用于服务健康检查，`GET /api/system/status` 用于展示当前 Python 运行时、操作系统、进程、线程、磁盘和数据记录情况。

## 运行文件

运行数据统一放在 `instance` 目录：SQLite 数据库位于 `instance/lost_found.db`，上传文件位于 `instance/uploads`，滚动日志位于 `instance/logs/backend.log`，备份位于 `instance/backups`。可通过 `APP_DATA_DIR` 改变数据目录，通过 `APP_HOST`、`APP_PORT`、`APP_DEBUG` 和 `APP_LOG_LEVEL` 配置运行环境。

课程知识点与实现之间的对应关系见 `TOOLCHAIN_DESIGN.md`。
