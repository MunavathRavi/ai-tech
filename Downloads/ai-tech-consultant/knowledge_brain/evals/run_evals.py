"""Eval for Task 1. Scores correctness (expected facts present), honesty (refuses unanswerable),
injection safety, citation validity, cost and latency per model.
Usage:  python -m evals.run_evals            (live, compares FAST vs SMART answer models)
        LLM_MODE=mock python -m evals.run_evals   (plumbing check only; numbers are meaningless)"""
import json, os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import config, llm, qa
from app.db import DB

def build_db(corpus):
    db = DB(os.path.join(tempfile.mkdtemp(), "eval.db"))
    for p in corpus:
        db.run("INSERT INTO pages(url,title,text,kind,status,updated_at) VALUES(?,?,?,'article','active',?)",
               (p["url"], p["title"], p["text"], time.time()))
        db.replace_chunks(p["url"], p["title"], "article", [f"{p['title']}\n{p['text']}"])
    return db

def run(model: str, data: dict) -> dict:

    db = build_db(data["corpus"]); llm.ledger.reset()
    urls = {p["url"] for p in data["corpus"]}
    ok, rows, t0 = 0, [], time.time()
    for c in data["cases"]:
        r = qa.ask(db, c["q"], model=model)
        text = r["answer"].lower()
        if c["answerable"]:
            hit = [e.lower() in text for e in c["expect"]]
            good = r["answered"] and (any(hit) if c.get("any") else all(hit)) \
                   and not any(f.lower() in text for f in c.get("forbid", [])) and set(r["sources"]) <= urls and r["sources"]
        else:
            good = not r["answered"]
        ok += bool(good); rows.append((c["q"], bool(good)))
    n = len(data["cases"])
    return {"model": model, "pass": ok, "total": n, "acc": ok / n, "usd": llm.ledger.total_usd(),
            "secs_per_q": (time.time() - t0) / n, "fails": [q for q, g in rows if not g]}

if __name__ == "__main__":
    data = json.load(open(pathlib.Path(__file__).with_name("cases.json")))
    results = [run(m, data) for m in dict.fromkeys([config.FAST_MODEL, config.SMART_MODEL])]
    print("| model | pass | accuracy | $ total | $ / question | sec / question |\n|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['model']} | {r['pass']}/{r['total']} | {r['acc']:.0%} | {r['usd']:.4f} | {r['usd']/r['total']:.5f} | {r['secs_per_q']:.2f} |")
    for r in results:
        if r["fails"]: print(f"\nFailures for {r['model']}:", *r["fails"], sep="\n  - ")
