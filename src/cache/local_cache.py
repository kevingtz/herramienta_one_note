from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("onenote_todo_sync")

CACHE_DIR = os.path.expanduser("~/.onenote-todo-sync")
CACHE_DB_PATH = os.path.join(CACHE_DIR, "sync_cache.db")


class SyncCache:
    """SQLite-backed cache for tracking synchronization state."""

    def __init__(self, db_path: str = CACHE_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS synced_tasks (
                task_id TEXT PRIMARY KEY,
                list_id TEXT NOT NULL,
                list_name TEXT NOT NULL,
                title TEXT NOT NULL,
                onenote_page_id TEXT,
                onenote_link TEXT,
                calendar_event_id TEXT,
                status TEXT NOT NULL,
                due_date TEXT,
                last_modified_todo TEXT,
                last_modified_local TEXT,
                needs_onenote INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                task_id TEXT,
                details TEXT,
                success INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS weekly_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                week_start TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def get_task(self, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM synced_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_tasks(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM synced_tasks").fetchall()
        return [dict(r) for r in rows]

    def get_tasks_by_list(self, list_name: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM synced_tasks WHERE list_name = ?", (list_name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_task(self, task_data: dict):
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_task(task_data["task_id"])

        if existing:
            self.conn.execute(
                """UPDATE synced_tasks SET
                    list_id=?, list_name=?, title=?, onenote_page_id=?,
                    onenote_link=?, calendar_event_id=?, status=?,
                    due_date=?, last_modified_todo=?, last_modified_local=?,
                    needs_onenote=?, updated_at=?
                WHERE task_id=?""",
                (
                    task_data.get("list_id", existing["list_id"]),
                    task_data.get("list_name", existing["list_name"]),
                    task_data.get("title", existing["title"]),
                    task_data.get("onenote_page_id", existing["onenote_page_id"]),
                    task_data.get("onenote_link", existing["onenote_link"]),
                    task_data.get("calendar_event_id", existing["calendar_event_id"]),
                    task_data.get("status", existing["status"]),
                    task_data.get("due_date", existing["due_date"]),
                    task_data.get("last_modified_todo", existing["last_modified_todo"]),
                    now,
                    task_data.get("needs_onenote", existing["needs_onenote"]),
                    now,
                    task_data["task_id"],
                ),
            )
        else:
            self.conn.execute(
                """INSERT INTO synced_tasks
                    (task_id, list_id, list_name, title, onenote_page_id,
                     onenote_link, calendar_event_id, status, due_date,
                     last_modified_todo, last_modified_local, needs_onenote,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_data["task_id"],
                    task_data["list_id"],
                    task_data["list_name"],
                    task_data["title"],
                    task_data.get("onenote_page_id"),
                    task_data.get("onenote_link"),
                    task_data.get("calendar_event_id"),
                    task_data["status"],
                    task_data.get("due_date"),
                    task_data.get("last_modified_todo"),
                    now,
                    task_data.get("needs_onenote", 0),
                    now,
                    now,
                ),
            )
        self.conn.commit()

    def delete_task(self, task_id: str):
        self.conn.execute("DELETE FROM synced_tasks WHERE task_id = ?", (task_id,))
        self.conn.commit()

    def log_action(self, action: str, task_id: str = None, details: str = None, success: bool = True):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO sync_log (timestamp, action, task_id, details, success) VALUES (?, ?, ?, ?, ?)",
            (now, action, task_id, details, 1 if success else 0),
        )
        self.conn.commit()

    def get_weekly_review(self, week_start: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM weekly_reviews WHERE week_start = ?", (week_start,)
        ).fetchone()
        return dict(row) if row else None

    def save_weekly_review(self, event_id: str, week_start: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO weekly_reviews (event_id, week_start, created_at) VALUES (?, ?, ?)",
            (event_id, week_start, now),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
