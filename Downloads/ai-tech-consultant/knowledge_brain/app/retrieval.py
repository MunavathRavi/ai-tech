import re
from .db import DB

_STOP = set("a an the is are was were be to of in on for and or how do does can i my me it this that with what when where why which".split())

def tokens(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in _STOP and len(t) > 1]

def search(db: DB, query_terms: list[str], k: int = 6) -> list[dict]:
    """BM25 over FTS5 (porter stemming). Terms are quoted, so user text can never inject FTS syntax."""
    terms = list(dict.fromkeys(t for q in query_terms for t in tokens(q)))[:24]
    if not terms: return []
    match = " OR ".join(f'"{t}"' for t in terms)
    rows = db.rows("SELECT text,url,title,kind,bm25(chunks) AS s FROM chunks WHERE chunks MATCH ? ORDER BY s LIMIT ?",
                   (match, k * 3))
    seen, out = {}, []
    for r in rows:                                              # keep the best chunk per (url, kind), max k
        key = (r["url"], r["kind"])
        if key in seen: continue
        seen[key] = 1
        out.append({"text": r["text"], "url": r["url"], "title": r["title"], "kind": r["kind"], "score": -r["s"]})
        if len(out) == k: break
    return out
