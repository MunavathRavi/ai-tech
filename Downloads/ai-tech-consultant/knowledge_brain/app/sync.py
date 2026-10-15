"""Initial full read and the daily refresh share one code path: diff the sitemap against what we hold,
queue only what changed, process the queue politely. The queue lives in SQLite, so a stop halfway
resumes where it left off instead of starting over."""
import asyncio, json, logging, time
from . import config
from .crawler import PoliteFetcher, collect_urls, extract_page, chunk_text
from .db import DB
from .vision import caption_images

log = logging.getLogger("sync")

async def _process(db: DB, fetcher: PoliteFetcher, url: str, lastmod: str | None, stats: dict) -> None:
    try:
        r = await fetcher.get(url)
        if r.status_code in (404, 410):
            db.remove_page(url); stats["removed"] += 1; db.mark(url, "done"); return
        r.raise_for_status()
        page = extract_page(r.text, url)
        old = db.rows("SELECT content_hash FROM pages WHERE url=? AND status='active'", (url,))
        if old and old[0]["content_hash"] == page["hash"]:
            db.run("UPDATE pages SET lastmod=? WHERE url=?", (lastmod, url)); stats["unchanged"] += 1
        else:
            db.run("INSERT INTO pages(url,title,category,folder,lastmod,content_hash,text,kind,status,updated_at) "
                   "VALUES(?,?,?,?,?,?,?, 'article','active',?) ON CONFLICT(url) DO UPDATE SET "
                   "title=excluded.title,category=excluded.category,folder=excluded.folder,lastmod=excluded.lastmod,"
                   "content_hash=excluded.content_hash,text=excluded.text,status='active',updated_at=excluded.updated_at",
                   (url, page["title"], page["category"], page["folder"], lastmod, page["hash"], page["text"], time.time()))
            db.replace_chunks(url, page["title"], "article", chunk_text(page["title"], page["text"]))
            caps = await caption_images(db, fetcher, url, page["title"], page["images"])
            db.replace_chunks(url, page["title"], "image", caps)
            stats["updated" if old else "added"] += 1
        db.mark(url, "done")
    except Exception as e:
        log.warning("failed %s: %s", url, e); stats["failed"] += 1; db.mark(url, "failed", str(e)[:300])

async def run_sync(db: DB, fetcher: PoliteFetcher, sitemap_url: str | None = None,
                   max_pages: int | None = None, deep: bool = False) -> dict:
    """deep=True re-fetches every page (use weekly) in case the sitemap has no usable lastmod."""
    started = time.time()
    stats = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "failed": 0}
    current = await collect_urls(fetcher, sitemap_url or config.SITEMAP_URL)
    known = {r["url"]: r["lastmod"] for r in db.rows("SELECT url,lastmod FROM pages WHERE status='active' AND kind='article'")}
    for url in set(known) - set(current):                      # removed from sitemap
        db.remove_page(url); stats["removed"] += 1
    todo = [u for u, lm in current.items()
            if u not in known or deep or (lm is not None and lm != known[u])]
    if max_pages: todo = todo[:max_pages]
    db.enqueue(todo)
    queue = db.pending()                                        # includes leftovers from an interrupted run
    sem = asyncio.Semaphore(config.CRAWL_CONCURRENCY)
    async def worker(u: str):
        async with sem: await _process(db, fetcher, u, current.get(u), stats)
    await asyncio.gather(*(worker(u) for u in queue))
    stats["queued"] = len(queue)
    db.run("INSERT INTO sync_runs(started,finished,stats) VALUES(?,?,?)", (started, time.time(), json.dumps(stats)))
    return stats
