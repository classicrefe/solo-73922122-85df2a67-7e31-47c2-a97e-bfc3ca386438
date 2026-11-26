"""SQLite 存储（标准库 sqlite3，嵌套数据以 JSON 存放）。"""
from __future__ import annotations

import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    pages_json TEXT NOT NULL,        -- 补白后的新版页序（JSON 数组，null = 空白页）
    old_sheets_json TEXT NOT NULL,   -- 提交的旧印张（JSON 数组）
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    work_order_id TEXT NOT NULL,
    pos_index INTEGER NOT NULL,      -- 0 = 最外张，从外到内递增
    required_json TEXT NOT NULL,     -- 新版拼版 {"front": {"left","right"}, "back": {...}}
    assignment TEXT NOT NULL,        -- 旧纸编号或 'NEW'（领新纸）
    faces_json TEXT NOT NULL,        -- 计划待印面，如 ["front"]
    status TEXT NOT NULL,            -- 'pending' | 'completed'
    dispatch_id TEXT NOT NULL,       -- 当前有效派工
    PRIMARY KEY (work_order_id, pos_index)
);
CREATE TABLE IF NOT EXISTS dispatches (
    id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    pos_index INTEGER NOT NULL,
    assignment TEXT NOT NULL,
    state TEXT NOT NULL,             -- 'active' | 'returned' | 'confirmed'
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scraps (
    work_order_id TEXT NOT NULL,
    sheet_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (work_order_id, sheet_id)
);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def init(path: str | None = None) -> sqlite3.Connection:
    """初始化（或重置）数据库连接。path 缺省取环境变量 DB_PATH。"""
    global _conn
    path = path or os.environ.get("DB_PATH", "data/app.db")
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new_conn = sqlite3.connect(path, check_same_thread=False)
    new_conn.row_factory = sqlite3.Row
    with new_conn:
        new_conn.executescript(SCHEMA)
    if _conn is not None and _conn is not new_conn:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = new_conn
    return new_conn


def conn() -> sqlite3.Connection:
    if _conn is None:
        init()
    return _conn


def lock() -> threading.RLock:
    return _lock
