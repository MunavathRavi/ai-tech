import sqlite3, threading, time
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, title TEXT, category TEXT, folder TEXT,
  lastmod TEXT, content_hash TEXT, text TEXT, kind TEXT DEFAULT 'article',
  status TEXT DEFAULT 'active', updated_at REAL);
CREATE TABLE IF NOT EXISTS images(src TEXT PRIMARY KEY, page_url TEXT, alt TEXT, caption TEXT);
CREATE TABLE IF NOT EXISTS queue(url TEXT PRIMARY KEY, status TEXT, attempts INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, status TEXT DEFAULT 'open',
  answer TEXT, asker TEXT, created_at REAL, answered_at REAL);
CREATE TABLE IF NOT EXISTS sync_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL, finished REAL, stats TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(text, url UNINDEXED, title UNINDEXED, kind UNINDEXED, tokenize='porter');
"""

class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA); self.conn.commit()

    def run(self, sql: str, args: Iterable[Any] = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, tuple(args)); self.conn.commit(); return cur.lastrowid or 0

    def rows(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchall()

    def replace_chunks(self, url: str, title: str, kind: str, texts: list[str]) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM chunks WHERE url=? AND kind=?", (url, kind))
            self.conn.executemany("INSERT INTO chunks(text,url,title,kind) VALUES(?,?,?,?)",
                                  [(t, url, title, kind) for t in texts])
            self.conn.commit()

    def remove_page(self, url: str) -> None:
        """A removed article must stop appearing in answers: delete chunks, tombstone the page."""
        with self.lock:
            self.conn.execute("DELETE FROM chunks WHERE url=?", (url,))
            self.conn.execute("UPDATE pages SET status='removed', updated_at=? WHERE url=?", (time.time(), url))
            self.conn.execute("DELETE FROM images WHERE page_url=?", (url,))
            self.conn.commit()

    # crawl queue: makes the first full read resumable after a crash or stop
    def enqueue(self, urls: list[str]) -> None:
        with self.lock:
            for u in urls:
                self.conn.execute("INSERT INTO queue(url,status) VALUES(?, 'pending') "
                                  "ON CONFLICT(url) DO UPDATE SET status='pending', attempts=0, error=NULL", (u,))
            self.conn.commit()

    def pending(self) -> list[str]:
        return [r["url"] for r in self.rows("SELECT url FROM queue WHERE status='pending' ORDER BY url")]

    def mark(self, url: str, status: str, error: str | None = None) -> None:
        self.run("UPDATE queue SET status=?, error=?, attempts=attempts+1 WHERE url=?", (status, error, url))
