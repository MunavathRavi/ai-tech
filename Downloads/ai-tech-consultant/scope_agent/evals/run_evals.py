"""Eval for Task 3: 20 cases (15 first meetings + 5 follow-ups).
Scores: requirement recall, out-of-scope capture, follow-up edit correctness (removed/changed/added/kept),
structural validity (every requirement has a task, no fake 'existing setting' claims), cost, speed.
Usage: python -m evals.run_evals     (live: compares configured model sets)
       LLM_MODE=mock python -m evals.run_evals   (plumbing only)
Model sets are compared by overriding the agent models below."""
import json, os, pathlib, sys, tempfile, time
import httpx
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import agents, config, llm
from app.brain_client import BrainClient
from app.orchestrator import process_meeting
from app.store import Store

def fake_brain() -> BrainClient:
    def h(req: httpx.Request) -> httpx.Response:
        q = json.loads(req.content)["question"].lower()
        if any(w in q for w in ("colour", "color", "hide", "banner")):
            return httpx.Response(200, json={"answered": True, "answer": "Use Design Settings or the page visibility toggle.", "sources": [{"url": "https://kb/x"}], "confidence": 0.9, "task_id": None})
        return httpx.Response(200, json={"answered": False, "answer": "", "sources": [], "confidence": 0, "task_id": 1})
    return BrainClient("http://b.test", "", transport=httpx.MockTransport(h), retries=0)

def has(reqs, kw): return any(kw.lower() in (r.title + " " + r.description).lower() for r in reqs)

def run_case(c: dict) -> dict:
    store = Store(tempfile.mkdtemp()); pid = store.create(c["id"]); brain = fake_brain()
    scope, _ = process_meeting(store, brain, pid, c["transcripts"])
    checks: dict[str, bool] = {}
    if c["kind"] == "single":
        live = [r for r in scope.requirements if r.status != "removed"]
        for kw in c["expect_requirements"]: checks[f"found:{kw}"] = has(live, kw)
        for kw in c["expect_out_of_scope"]: checks[f"oos:{kw}"] = any(kw.lower() in o.lower() for o in scope.out_of_scope)
        checks["no_runaway"] = len(live) <= len(c["expect_requirements"]) + 2
    else:
        s1_tasks = {t.title for t in scope.tasks}
        scope, _ = process_meeting(store, brain, pid, [c["followup"]])
        e = c["expect"]
        for kw in e.get("removed", []):
            r = [x for x in scope.requirements if kw in (x.title + x.description).lower()]
            checks[f"removed:{kw}"] = bool(r) and all(x.status == "removed" for x in r)
        for kw in e.get("changed", []): checks[f"changed:{kw}"] = any(x.status == "changed" and kw in (x.title + x.description).lower() for x in scope.requirements)
        for kw in e.get("added", []): checks[f"added:{kw}"] = any(x.status == "new" and kw in (x.title + x.description).lower() for x in scope.requirements)
        for kw in e.get("kept", []): checks[f"kept:{kw}"] = any(x.status == "unchanged" and kw in (x.title + x.description).lower() for x in scope.requirements)
        checks["untouched_tasks_survive"] = bool(s1_tasks & {t.title for t in scope.tasks}) or not e.get("kept")
    checks["valid_structure"] = not agents.validate(scope)
    return checks

def main() -> None:
    cases = json.load(open(pathlib.Path(__file__).with_name("cases.json")))
    llm.ledger.reset(); t0 = time.time(); passed = total = full = 0; fails = []
    for c in cases:
        checks = run_case(c)
        total += len(checks); passed += sum(checks.values()); full += all(checks.values())
        fails += [f"{c['id']}:{k}" for k, v in checks.items() if not v]
    print("| models (extractor/estimator) | checks passed | cases fully correct | $ total | s / case |\n|---|---|---|---|---|")
    print(f"| {config.AGENT_MODELS['extractor']} / {config.AGENT_MODELS['estimator']} | {passed}/{total} ({passed/total:.0%}) | {full}/{len(cases)} | {llm.ledger.total_usd():.4f} | {(time.time()-t0)/len(cases):.2f} |")
    if fails: print("\nFailed checks:", *fails, sep="\n  - ")

if __name__ == "__main__": main()
