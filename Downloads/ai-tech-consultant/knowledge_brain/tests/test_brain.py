import httpx, pytest
from app.crawler import PoliteFetcher
from app.db import DB
from app.sync import run_sync
from app import qa

def sitemap(pages):
    body = "".join(f"<url><loc>{u}</loc><lastmod>{lm}</lastmod></url>" for u, lm in pages.items())
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'

def page(title, body, img=None):
    im = f'<img src="{img}" alt="settings screen">' if img else ""
    return (f"<html><body><ol class='breadcrumb'><li>Home</li><li>Payments</li><li>Refunds</li><li>{title}</li></ol>"
            f"<article><h1>{title}</h1><p>{body}</p>{im}</article></body></html>")

class Site:
    def __init__(self): self.pages = {}; self.lastmod = {}; self.hits = []
    def handler(self, req: httpx.Request) -> httpx.Response:
        self.hits.append(str(req.url))
        u = str(req.url)
        if u.endswith("sitemap.xml"): return httpx.Response(200, text=sitemap(self.lastmod))
        if u.endswith(".png"): return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        if u in self.pages: return httpx.Response(200, text=self.pages[u])
        return httpx.Response(404)

A, B = "https://h.test/a", "https://h.test/b"
def setup(tmp_path):
    site = Site()
    site.pages = {A: page("Refund policy", "Refunds are issued within 14 days of purchase to the original card.", "https://h.test/x.png"),
                  B: page("Change theme", "Open Design Settings and choose a new theme colour.")}
    site.lastmod = {A: "2026-01-01", B: "2026-01-01"}
    f = PoliteFetcher(transport=httpx.MockTransport(site.handler), min_delay=0, retries=1)
    return site, DB(str(tmp_path / "t.db")), f

async def test_full_read_then_answer_with_citation(tmp_path):
    site, db, f = setup(tmp_path)
    s = await run_sync(db, f, "https://h.test/sitemap.xml")
    assert s["added"] == 2 and s["failed"] == 0
    r = qa.ask(db, "how many days do refunds take")
    assert r["answered"] and r["sources"] == [A]
    assert db.rows("SELECT COUNT(*) c FROM chunks WHERE kind='image'")[0]["c"] == 1   # screenshot indexed

async def test_unknown_question_creates_task_and_expert_answer_flows_back(tmp_path):
    site, db, f = setup(tmp_path)
    await run_sync(db, f, "https://h.test/sitemap.xml")
    r = qa.ask(db, "do you support quantum billing")
    assert not r["answered"] and r["task_id"]
    qa.answer_task(db, r["task_id"], "Quantum billing is on the roadmap for next year.")
    r2 = qa.ask(db, "do you support quantum billing")
    assert r2["answered"] and r2["sources"][0].startswith("expert://")

async def test_daily_sync_updates_only_what_changed_and_removed_stops_appearing(tmp_path):
    site, db, f = setup(tmp_path)
    await run_sync(db, f, "https://h.test/sitemap.xml")
    site.hits.clear()
    site.pages[A] = page("Refund policy", "Refunds are issued within 30 days of purchase.")
    site.lastmod[A] = "2026-02-01"
    del site.lastmod[B]
    s = await run_sync(db, f, "https://h.test/sitemap.xml")
    assert s["updated"] == 1 and s["removed"] == 1
    assert not any(h.endswith("/b") for h in site.hits)                  # unchanged/removed pages not re-fetched
    assert "30 days" in qa.ask(db, "refund days")["answer"]
    assert qa.ask(db, "change theme colour")["answered"] is False       # removed article no longer answers

async def test_interrupted_sync_resumes_from_queue(tmp_path):
    site, db, f = setup(tmp_path)
    db.enqueue([A, B])                                                   # simulate crash after enqueue
    s = await run_sync(db, f, "https://h.test/sitemap.xml")
    assert s["added"] == 2 and db.pending() == []

async def test_server_errors_are_retried_then_recorded_not_fatal(tmp_path):
    site, db, f = setup(tmp_path)
    orig = site.handler
    site.handler = lambda req: httpx.Response(500) if str(req.url) == B else orig(req)
    f.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: site.handler(r)))
    s = await run_sync(db, f, "https://h.test/sitemap.xml")
    assert s["added"] == 1 and s["failed"] == 1

def test_prompt_injection_in_question_cannot_break_fts(tmp_path):
    from app.retrieval import search
    db = DB(str(tmp_path / "x.db"))
    assert search(db, ['" OR 1=1 --', "NEAR(", "*", "AND OR NOT"]) == []   # hostile text is quoted, never parsed as FTS syntax
