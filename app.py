"""AI 失物招领平台：单文件 Python Flask 后端。"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = INSTANCE_DIR / "uploads"
DATABASE = INSTANCE_DIR / "lost_found.db"
ALLOWED_IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
CATEGORIES = {"digital", "card", "daily", "other"}

INSTANCE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "*"}})


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('lost', 'found')),
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    occurred_at TEXT,
    contact TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'claimed', 'closed')),
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    applicant_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    proof TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by INTEGER,
    reviewed_at TEXT,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(item_id, applicant_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (applicant_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL,
    sender_id INTEGER,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    related_item_id INTEGER,
    related_claim_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (recipient_id) REFERENCES users(id),
    FOREIGN KEY (sender_id) REFERENCES users(id),
    FOREIGN KEY (related_item_id) REFERENCES items(id),
    FOREIGN KEY (related_claim_id) REFERENCES claims(id)
);

CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at);
CREATE INDEX IF NOT EXISTS idx_claims_item_id ON claims(item_id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, is_read);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    connection = connect_db()
    connection.executescript(SCHEMA)
    connection.close()


def success(data=None, message="ok", status=200):
    return jsonify({"code": 0, "message": message, "data": data}), status


def error(message, status=400):
    return jsonify({"code": status, "message": message, "data": None}), status


def body_data() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def positive_int(value, default: int, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(number, 1)
    return min(number, maximum) if maximum is not None else number


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    database = get_db()
    database.execute(
        "INSERT INTO auth_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
        (token_hash(token), user_id, expires_at.isoformat(), now_iso()),
    )
    database.commit()
    return token


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return error("missing or invalid Authorization header", 401)

        token = authorization.removeprefix("Bearer ").strip()
        row = get_db().execute(
            """
            SELECT users.* FROM auth_tokens
            JOIN users ON users.id = auth_tokens.user_id
            WHERE auth_tokens.token_hash = ? AND auth_tokens.expires_at > ?
            """,
            (token_hash(token), datetime.now(timezone.utc).isoformat()),
        ).fetchone()
        if row is None:
            return error("access token is invalid or expired", 401)

        g.current_user = dict(row)
        g.current_token = token
        return view(*args, **kwargs)

    return wrapped


def public_user(row, include_phone=False):
    data = {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"] or row["username"],
        "created_at": row["created_at"],
    }
    if include_phone:
        data["phone"] = row["phone"]
    return data


def item_dict(row):
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "category": row["category"],
        "description": row["description"],
        "location": row["location"],
        "occurred_at": row["occurred_at"],
        "contact": row["contact"],
        "image_url": row["image_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "owner": {
            "id": row["owner_id"],
            "username": row["owner_username"],
            "nickname": row["owner_nickname"] or row["owner_username"],
        },
    }


ITEM_SELECT = """
SELECT items.*, users.id AS owner_id, users.username AS owner_username,
       users.nickname AS owner_nickname
FROM items JOIN users ON users.id = items.user_id
"""


def get_item(item_id: int):
    return get_db().execute(ITEM_SELECT + " WHERE items.id = ?", (item_id,)).fetchone()


def save_image(file) -> str:
    if file is None or not file.filename:
        raise ValueError("image file is required")
    extension = Path(secure_filename(file.filename)).suffix.lower().lstrip(".")
    if extension not in ALLOWED_IMAGE_TYPES:
        raise ValueError("unsupported image type")
    filename = f"{secrets.token_hex(12)}.{extension}"
    destination = UPLOAD_DIR / filename
    file.save(destination)
    try:
        with Image.open(destination) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exception:
        destination.unlink(missing_ok=True)
        raise ValueError("the uploaded file is not a valid image") from exception
    return f"/uploads/{filename}"


def notify(recipient_id, sender_id, message_type, title, content, item_id=None, claim_id=None):
    timestamp = now_iso()
    get_db().execute(
        """
        INSERT INTO messages(recipient_id,sender_id,type,title,content,related_item_id,
                             related_claim_id,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (recipient_id, sender_id, message_type, title, content, item_id, claim_id, timestamp, timestamp),
    )


@app.get("/")
def root():
    return jsonify({"name": "AI lost and found Python API", "status": "running"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/auth/register")
def register():
    data = body_data()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if len(username) < 3 or len(username) > 32:
        return error("username must be between 3 and 32 characters")
    if len(password) < 6:
        return error("password must be at least 6 characters")

    database = get_db()
    try:
        cursor = database.execute(
            "INSERT INTO users(username,password_hash,nickname,phone,created_at) VALUES(?,?,?,?,?)",
            (
                username,
                generate_password_hash(password),
                str(data.get("nickname", "")).strip()[:64],
                str(data.get("phone", "")).strip()[:32],
                now_iso(),
            ),
        )
        database.commit()
    except sqlite3.IntegrityError:
        return error("username is already taken", 409)

    user = database.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return success(
        {"token": issue_token(user["id"]), "user": public_user(user, True)},
        "registered",
        201,
    )


@app.post("/api/auth/login")
def login():
    data = body_data()
    user = get_db().execute(
        "SELECT * FROM users WHERE username = ?",
        (str(data.get("username", "")).strip(),),
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], str(data.get("password", ""))):
        return error("invalid username or password", 401)
    return success({"token": issue_token(user["id"]), "user": public_user(user, True)}, "logged in")


@app.get("/api/auth/me")
@login_required
def me():
    return success(public_user(g.current_user, True))


@app.post("/api/auth/logout")
@login_required
def logout():
    database = get_db()
    database.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash(g.current_token),))
    database.commit()
    return success(message="logged out")


@app.get("/api/items")
def list_items():
    conditions = []
    parameters = []
    item_type = request.args.get("type", "")
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    page = positive_int(request.args.get("page"), 1)
    page_size = positive_int(request.args.get("page_size"), 12, 100)

    if item_type in {"lost", "found"}:
        conditions.append("items.type = ?")
        parameters.append(item_type)
    if category in CATEGORIES:
        conditions.append("items.category = ?")
        parameters.append(category)
    if status in {"open", "claimed", "closed"}:
        conditions.append("items.status = ?")
        parameters.append(status)
    if keyword:
        conditions.append("(items.title LIKE ? OR items.location LIKE ? OR items.description LIKE ?)")
        parameters.extend([f"%{keyword}%"] * 3)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    database = get_db()
    total = database.execute("SELECT COUNT(*) FROM items" + where, parameters).fetchone()[0]
    rows = database.execute(
        ITEM_SELECT + where + " ORDER BY items.created_at DESC, items.id DESC LIMIT ? OFFSET ?",
        [*parameters, page_size, (page - 1) * page_size],
    ).fetchall()
    return success({
        "items": [item_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    })


@app.post("/api/items")
@login_required
def create_item():
    data = body_data()
    item_type = str(data.get("type", "")).strip()
    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "other")).strip() or "other"
    if item_type not in {"lost", "found"}:
        return error("type must be 'lost' or 'found'")
    if not title:
        return error("title is required")
    if category not in CATEGORIES:
        return error("invalid category")

    try:
        image_url = save_image(request.files.get("image")) if request.files.get("image") else ""
    except ValueError as exception:
        return error(str(exception))

    timestamp = now_iso()
    database = get_db()
    cursor = database.execute(
        """
        INSERT INTO items(type,title,category,description,location,occurred_at,contact,
                          image_url,status,user_id,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            item_type, title[:120], category, str(data.get("description", ""))[:5000],
            str(data.get("location", ""))[:255], str(data.get("occurred_at", "")) or None,
            str(data.get("contact", ""))[:255], image_url, "open", g.current_user["id"],
            timestamp, timestamp,
        ),
    )
    database.commit()
    return success(item_dict(get_item(cursor.lastrowid)), "item published", 201)


@app.get("/api/items/<int:item_id>")
def item_detail(item_id):
    row = get_item(item_id)
    if row is None:
        return error("item not found", 404)
    data = item_dict(row)
    data["claim_count"] = get_db().execute(
        "SELECT COUNT(*) FROM claims WHERE item_id = ?", (item_id,)
    ).fetchone()[0]
    return success(data)


@app.patch("/api/items/<int:item_id>")
@login_required
def update_item(item_id):
    row = get_item(item_id)
    if row is None:
        return error("item not found", 404)
    if row["user_id"] != g.current_user["id"]:
        return error("only the publisher can edit this item", 403)
    data = body_data()
    fields = {
        "type": data.get("type", row["type"]),
        "title": str(data.get("title", row["title"])).strip(),
        "category": data.get("category", row["category"]),
        "description": data.get("description", row["description"]),
        "location": data.get("location", row["location"]),
        "occurred_at": data.get("occurred_at", row["occurred_at"]),
        "contact": data.get("contact", row["contact"]),
        "image_url": row["image_url"],
    }
    if fields["type"] not in {"lost", "found"} or not fields["title"]:
        return error("invalid item data")
    if fields["category"] not in CATEGORIES:
        return error("invalid category")
    if request.files.get("image"):
        try:
            fields["image_url"] = save_image(request.files["image"])
        except ValueError as exception:
            return error(str(exception))
    database = get_db()
    database.execute(
        """UPDATE items SET type=?,title=?,category=?,description=?,location=?,occurred_at=?,
           contact=?,image_url=?,updated_at=? WHERE id=?""",
        (*fields.values(), now_iso(), item_id),
    )
    database.commit()
    return success(item_dict(get_item(item_id)), "item updated")


@app.post("/api/items/<int:item_id>/close")
@login_required
def close_item(item_id):
    row = get_item(item_id)
    if row is None:
        return error("item not found", 404)
    if row["user_id"] != g.current_user["id"]:
        return error("only the publisher can close this item", 403)
    database = get_db()
    database.execute("UPDATE items SET status='closed',updated_at=? WHERE id=?", (now_iso(), item_id))
    database.commit()
    return success(item_dict(get_item(item_id)), "item closed")


@app.post("/api/uploads")
@login_required
def upload():
    try:
        return success({"url": save_image(request.files.get("image"))}, "uploaded", 201)
    except ValueError as exception:
        return error(str(exception))


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.post("/api/ai/recognize")
def recognize_image():
    try:
        image_url = save_image(request.files.get("image"))
    except ValueError as exception:
        return error(str(exception))

    image_path = UPLOAD_DIR / image_url.removeprefix("/uploads/")
    with Image.open(image_path) as image:
        red, green, blue = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        width, height = image.size
    brightness = (red + green + blue) / 3
    if brightness < 80:
        title, category = "深色数码电子设备", "digital"
    elif 0.9 <= width / max(height, 1) <= 1.5 and brightness > 180:
        title, category = "证件或卡片", "card"
    else:
        title, category = "待确认日用品", "daily"
    labels = {"digital": "数码电子", "card": "证件卡片", "daily": "日用品"}
    return success({
        "title": title,
        "category": category,
        "category_label": labels[category],
        "confidence": 0.68,
        "keywords": [labels[category]],
        "image_url": image_url,
    }, "recognition completed")


@app.post("/api/items/<int:item_id>/claims")
@login_required
def create_claim(item_id):
    item = get_item(item_id)
    if item is None:
        return error("item not found", 404)
    if item["type"] != "found" or item["status"] != "open":
        return error("this item is not available for claiming")
    if item["user_id"] == g.current_user["id"]:
        return error("you cannot claim an item you published")
    data = body_data()
    description = str(data.get("description", "")).strip()
    if not description:
        return error("description is required")
    timestamp = now_iso()
    database = get_db()
    try:
        cursor = database.execute(
            """INSERT INTO claims(item_id,applicant_id,description,proof,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (item_id, g.current_user["id"], description, str(data.get("proof", "")), "pending", timestamp, timestamp),
        )
    except sqlite3.IntegrityError:
        return error("you have already submitted a claim for this item", 409)
    notify(item["user_id"], g.current_user["id"], "claim_submitted", "收到新的认领申请",
           f"{g.current_user['username']} 申请认领「{item['title']}」", item_id, cursor.lastrowid)
    database.commit()
    return success({"id": cursor.lastrowid, "status": "pending"}, "claim submitted", 201)


@app.get("/api/items/<int:item_id>/claims")
@login_required
def list_claims(item_id):
    item = get_item(item_id)
    if item is None:
        return error("item not found", 404)
    if item["user_id"] != g.current_user["id"]:
        return error("only the publisher can view claim applications", 403)
    rows = get_db().execute(
        """SELECT claims.*, users.username, users.nickname FROM claims
           JOIN users ON users.id=claims.applicant_id WHERE item_id=? ORDER BY claims.created_at DESC""",
        (item_id,),
    ).fetchall()
    claims = [{
        "id": row["id"], "item_id": row["item_id"], "description": row["description"],
        "proof": row["proof"], "status": row["status"], "review_note": row["review_note"],
        "created_at": row["created_at"],
        "applicant": {"id": row["applicant_id"], "username": row["username"],
                      "nickname": row["nickname"] or row["username"]},
    } for row in rows]
    return success({"claims": claims, "total": len(claims), "page": 1, "page_size": len(claims), "pages": 1})


@app.patch("/api/claims/<int:claim_id>/review")
@login_required
def review_claim(claim_id):
    database = get_db()
    claim = database.execute(
        """SELECT claims.*, items.user_id AS owner_id, items.title AS item_title,
           items.status AS item_status FROM claims JOIN items ON items.id=claims.item_id
           WHERE claims.id=?""", (claim_id,)
    ).fetchone()
    if claim is None:
        return error("claim not found", 404)
    if claim["owner_id"] != g.current_user["id"]:
        return error("only the publisher can review this claim", 403)
    if claim["status"] != "pending":
        return error("only pending claims can be reviewed")
    data = body_data()
    action = data.get("action")
    if action not in {"approve", "reject"}:
        return error("action must be 'approve' or 'reject'")
    status = "approved" if action == "approve" else "rejected"
    timestamp = now_iso()
    database.execute(
        "UPDATE claims SET status=?,reviewed_by=?,reviewed_at=?,review_note=?,updated_at=? WHERE id=?",
        (status, g.current_user["id"], timestamp, str(data.get("note", "")), timestamp, claim_id),
    )
    if action == "approve":
        database.execute("UPDATE items SET status='claimed',updated_at=? WHERE id=?", (timestamp, claim["item_id"]))
        database.execute(
            """UPDATE claims SET status='rejected',review_note='物品已被其他人成功认领',
               reviewed_by=?,reviewed_at=?,updated_at=?
               WHERE item_id=? AND id<>? AND status='pending'""",
            (g.current_user["id"], timestamp, timestamp, claim["item_id"], claim_id),
        )
    notify(claim["applicant_id"], g.current_user["id"], "claim_reviewed",
           "认领申请已通过" if action == "approve" else "认领申请未通过",
           f"你对「{claim['item_title']}」的认领申请{('已通过' if action == 'approve' else '未通过')}。",
           claim["item_id"], claim_id)
    database.commit()
    return success({"id": claim_id, "status": status}, "claim reviewed")


@app.get("/api/messages")
@login_required
def messages():
    rows = get_db().execute(
        "SELECT * FROM messages WHERE recipient_id=? ORDER BY created_at DESC",
        (g.current_user["id"],),
    ).fetchall()
    data = [dict(row) for row in rows]
    for message in data:
        message["is_read"] = bool(message["is_read"])
    return success({"messages": data, "total": len(data), "page": 1, "page_size": len(data), "pages": 1})


@app.patch("/api/messages/<int:message_id>/read")
@login_required
def read_message(message_id):
    database = get_db()
    database.execute(
        "UPDATE messages SET is_read=1,updated_at=? WHERE id=? AND recipient_id=?",
        (now_iso(), message_id, g.current_user["id"]),
    )
    database.commit()
    return success(message="message marked as read")


init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
