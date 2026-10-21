# 单文件 Python 后端版

这是一份重新整理的纯 Python 后端，所有核心代码都在 `app.py` 中，适合学习、演示和课程答辩。

## 运行

Windows 双击 `start.bat`，或者执行：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

`start.bat` 默认使用独立端口，服务地址：`http://127.0.0.1:5003`

直接执行 `python app.py` 时默认使用 `5000` 端口，也可以先设置 `PORT` 环境变量修改端口。

## 前端调用

```javascript
const response = await fetch("http://127.0.0.1:5003/api/items");
const result = await response.json();
console.log(result.data.items);
```

需要登录的接口使用：

```javascript
headers: {
  Authorization: `Bearer ${localStorage.getItem("token")}`
}
```

本版本主要接口与之前保持一致：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET/POST /api/items`
- `GET/PATCH /api/items/<id>`
- `POST /api/ai/recognize`
- `POST /api/items/<id>/claims`
- `PATCH /api/claims/<id>/review`
- `GET /api/messages`

浏览器页面仍需使用 HTML/CSS/JavaScript，因为浏览器不能直接执行 Python。Python 负责数据库、业务逻辑和 API。
