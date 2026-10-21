"""Command-line toolchain for running and maintaining the backend."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import app as backend


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def command_serve(arguments) -> int:
    backend.app.run(
        host=arguments.host,
        port=arguments.port,
        debug=arguments.debug,
        use_reloader=arguments.debug,
    )
    return 0


def command_init_db(arguments) -> int:
    backend.init_db()
    print_json({"status": "ok", "database": str(backend.DATABASE)})
    return 0


def command_check(arguments) -> int:
    checks = {"database": False, "uploads_writable": False, "logs_writable": False}
    try:
        connection = backend.connect_db()
        connection.execute("SELECT 1").fetchone()
        connection.close()
        checks["database"] = True
    except sqlite3.Error:
        pass

    checks["uploads_writable"] = os.access(backend.UPLOAD_DIR, os.W_OK)
    checks["logs_writable"] = os.access(backend.LOG_DIR, os.W_OK)
    healthy = all(checks.values())
    print_json({"status": "ok" if healthy else "failed", "checks": checks})
    return 0 if healthy else 1


def command_backup(arguments) -> int:
    destination = Path(arguments.output) if arguments.output else None
    backup = backend.create_database_backup(destination)
    print_json({"status": "ok", "backup": str(backup), "bytes": backup.stat().st_size})
    return 0


def command_system_info(arguments) -> int:
    print_json(backend.runtime_status())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 失物招领后端操作系统工具链")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="启动 HTTP 服务进程")
    serve.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "5003")))
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(handler=command_serve)

    init_db = commands.add_parser("init-db", help="初始化 SQLite 文件和数据表")
    init_db.set_defaults(handler=command_init_db)

    check = commands.add_parser("check", help="检查数据库和目录权限")
    check.set_defaults(handler=command_check)

    backup = commands.add_parser("backup", help="在线备份 SQLite 数据库")
    backup.add_argument("--output", help="可选的备份文件路径")
    backup.set_defaults(handler=command_backup)

    system_info = commands.add_parser("system-info", help="显示进程、运行时和存储信息")
    system_info.set_defaults(handler=command_system_info)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    return arguments.handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
