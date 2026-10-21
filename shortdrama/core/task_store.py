"""SQLite 任务持久化 + 断点续传。

存什么:
- 每个下载任务的元信息(url / 标题 / 保存路径 / 大小 / 状态)
- 已完成字节数,断点续传用
- 失败原因(方便重试)

Schema:
    tasks(
        id INTEGER PK,
        gid TEXT,                -- aria2 gid 或本地任务 id
        platform TEXT,
        drama_title TEXT,
        episode_title TEXT,
        episode_index INTEGER,
        url TEXT,
        save_path TEXT,
        total_size INTEGER,
        done_size INTEGER,
        status TEXT,             -- queued / downloading / paused / done / failed
        engine TEXT,             -- aria2 / yt-dlp / native
        error TEXT,
        created_at INTEGER,
        updated_at INTEGER
    )
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Task:
    id: int
    gid: str
    platform: str
    drama_title: str
    episode_title: str
    episode_index: int
    url: str
    save_path: str
    total_size: int
    done_size: int
    status: str
    engine: str
    error: str
    created_at: int
    updated_at: int


class TaskStore:
    def __init__(self, db_path: str = "./shortdrama_tasks.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gid TEXT,
                    platform TEXT,
                    drama_title TEXT,
                    episode_title TEXT,
                    episode_index INTEGER,
                    url TEXT,
                    save_path TEXT,
                    total_size INTEGER DEFAULT 0,
                    done_size INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'queued',
                    engine TEXT DEFAULT 'aria2',
                    error TEXT,
                    created_at INTEGER,
                    updated_at INTEGER
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")

    # ---------- 任务管理 ----------
    def add_task(self, *, platform: str, drama_title: str, episode_title: str,
                 episode_index: int, url: str, save_path: str, engine: str) -> int:
        now = int(time.time())
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO tasks
                (gid, platform, drama_title, episode_title, episode_index,
                 url, save_path, status, engine, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """, ("", platform, drama_title, episode_title, episode_index,
                  url, save_path, engine, now, now))
            return cur.lastrowid

    def update_task(self, task_id: int, **kwargs):
        if not kwargs:
            return
        kwargs["updated_at"] = int(time.time())
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        with self._conn() as c:
            c.execute(f"UPDATE tasks SET {cols} WHERE id=?", vals)

    def set_gid(self, task_id: int, gid: str):
        self.update_task(task_id, gid=gid, status="downloading")

    def mark_done(self, task_id: int, total_size: int):
        self.update_task(task_id, status="done", total_size=total_size,
                         done_size=total_size)

    def mark_failed(self, task_id: int, error: str):
        self.update_task(task_id, status="failed", error=error)

    def list_tasks(self, status: str | None = None, limit: int = 100) -> list[Task]:
        with self._conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def resumable_tasks(self) -> list[Task]:
        """启动时拉出所有未完成的:queued / downloading / paused。"""
        out = []
        for st in ("downloading", "paused", "queued"):
            out.extend(self.list_tasks(status=st))
        return out

    def clear_finished(self, keep_days: int = 7):
        cutoff = int(time.time()) - keep_days * 86400
        with self._conn() as c:
            c.execute(
                "DELETE FROM tasks WHERE status IN ('done','failed') AND updated_at < ?",
                (cutoff,),
            )

    def delete_task(self, task_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM tasks WHERE id=?", (task_id,))