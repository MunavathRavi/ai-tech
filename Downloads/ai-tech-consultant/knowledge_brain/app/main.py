import asyncio, contextlib, secrets
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from . import config, qa
from .crawler import PoliteFetcher
from .db import DB
from .retrieval import search
from .sync import run_sync

db = DB(config.DB_PATH)
sync_state = {"running": False, "last": None}

async def _do_sync(deep: bool = False, max_pages: int | None = None) -> None:
    if sync_state["running"]: return
    sync_state["running"] = True
    fetcher = PoliteFetcher()
    try: sync_state["last"] = await run_sync(db, fetcher, deep=deep, max_pages=max_pages)
    finally:
        sync_state["running"] = False; await fetcher.close()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if config.SYNC_INTERVAL_HOURS > 0:
        async def loop():
            while True:
                await _do_sync(); await asyncio.sleep(config.SYNC_INTERVAL_HOURS * 3600)
        task = asyncio.create_task(loop())
    yield
    if task: task.cancel()

def auth(x_api_key: str = Header(default="")) -> None:
    if config.API_KEY and not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(401, "bad api key")

app = FastAPI(title="Knowledge Brain", version="1.0", lifespan=lifespan, dependencies=[Depends(auth)],
              description="Memory + chatbot over a public help center. Tasks 2 and 3 use only this API.")

class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    asker: str | None = None
class Source(BaseModel):
    url: str; title: str | None = None
class AskOut(BaseModel):
    answered: bool; answer: str; sources: list[Source]; confidence: float; task_id: int | None
class SearchOut(BaseModel):
    url: str; title: str; kind: str; score: float; text: str
class ExpertIn(BaseModel):
    answer: str = Field(min_length=3, max_length=5000)

@app.get("/health")
def health():
    n = db.rows("SELECT COUNT(*) c FROM pages WHERE status='active'")[0]["c"]
    return {"ok": True, "active_pages": n, "sync": sync_state}

@app.post("/ask", response_model=AskOut)
def ask(body: AskIn):
    r = qa.ask(db, body.question, body.asker)
    titles = {p["url"]: p["title"] for p in db.rows("SELECT url,title FROM pages")}
    return AskOut(**{**r, "sources": [Source(url=u, title=titles.get(u)) for u in r["sources"]]})

@app.get("/search", response_model=list[SearchOut])
def search_ep(q: str, k: int = 5):
    return search(db, [q], min(max(k, 1), 20))

@app.post("/sync", status_code=202)
def trigger_sync(bg: BackgroundTasks, deep: bool = False, max_pages: int | None = None):
    if sync_state["running"]: raise HTTPException(409, "sync already running")
    bg.add_task(_do_sync, deep, max_pages); return {"started": True}

@app.get("/tasks")
def tasks(status: str = "open"):
    return [dict(r) for r in db.rows("SELECT * FROM tasks WHERE status=? ORDER BY id", (status,))]

@app.post("/tasks/{task_id}/answer")
def answer(task_id: int, body: ExpertIn):
    try: qa.answer_task(db, task_id, body.answer)
    except KeyError: raise HTTPException(404, "no open task with that id")
    return {"ok": True}
