"""Five agents, each with ONE job and one typed output. Handoffs:
Extractor/Updater -> Clarifier -> BrainChecker -> Estimator <-> Reviewer -> Writer."""
import re
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar
from pydantic import BaseModel
from . import config, llm, prompts
from .brain_client import BrainClient
from .models import (ClarifyOut, EstimateOut, ExtractOut, Finding, Question, ProposalOut, Requirement,
                     ReviewOut, Scope, Task, TaskIn, UpdateOut)

T = TypeVar("T", bound=BaseModel)

def _call(model_cls: type[T], agent: str, system: str, user: str, mock, max_tokens: int = 2500) -> T:
    out = llm.structured(system, user, model_cls.model_json_schema(), model=config.AGENT_MODELS[agent],
                         mock=lambda: mock().model_dump(), max_tokens=max_tokens)
    return model_cls.model_validate(out)

_WORDS = lambda s: set(re.findall(r"[a-z]{4,}", s.lower()))
_NEED = re.compile(r"\b(need|want|would like|can you|should|please add|build|make|add|must|looking for)\b", re.I)
_DROP = re.compile(r"\b(drop|forget|no longer|don't need|do not need|remove|cancel|scrap)\b", re.I)
_VAGUE = re.compile(r"\b(better|nicer|modern|improve|faster|easier|good)\b", re.I)

def _client_lines(transcript: str) -> list[str]:
    return [l.split(":", 1)[1].strip() for l in transcript.splitlines() if l.upper().startswith("CLIENT:")]

# ---------------------------------------------------------------- 1. Extractor
def extract(transcripts: list[str]) -> ExtractOut:
    joined = "\n\n=== NEXT MEETING ===\n\n".join(t[:30_000] for t in transcripts)
    def mock() -> ExtractOut:
        reqs = [ReqIn_(l) for t in transcripts for l in _client_lines(t) if _NEED.search(l) and not _DROP.search(l)]
        return ExtractOut(requirements=reqs, out_of_scope=[l for t in transcripts for l in _client_lines(t) if _DROP.search(l)])
    return _call(ExtractOut, "extractor", prompts.EXTRACTOR, f"TRANSCRIPT(S):\n{joined}", mock)

def ReqIn_(line: str):
    from .models import ReqIn
    title = re.sub(r"^(we|i)\s+(also\s+)?(need|want|would like)( to)?\s+", "", line.strip(), flags=re.I)[:70]
    return ReqIn(title=title.rstrip(".?!"), description=line, quote=line, vague=bool(_VAGUE.search(line)),
                 priority="must" if re.search(r"\b(must|need|have to)\b", line, re.I) else "should")

# ---------------------------------------------------------------- 1b. Updater (follow-up meetings)
def update(current: list[Requirement], transcript: str) -> UpdateOut:
    cur = "\n".join(f"{r.id}: {r.title} — {r.description}" for r in current if r.status != "removed")
    def mock() -> UpdateOut:
        from .models import Op
        ops: list[Op] = []; seen: set[str] = set()
        for line in _client_lines(transcript):
            lw = _WORDS(line)
            best = max((r for r in current if r.status != "removed"), key=lambda r: len(lw & _WORDS(r.title + " " + r.description)), default=None)
            overlap = len(lw & _WORDS(best.title + " " + best.description)) if best else 0
            if best and overlap >= 2 and _DROP.search(line):
                ops.append(Op(action="remove", requirement_id=best.id, reason=line)); seen.add(best.id)
            elif best and overlap >= 2 and best.id not in seen and _NEED.search(line):
                ops.append(Op(action="change", requirement_id=best.id, title=best.title, description=f"{best.description} UPDATE: {line}", quote=line, reason=line)); seen.add(best.id)
            elif _NEED.search(line) and not _DROP.search(line):
                r = ReqIn_(line); ops.append(Op(action="add", title=r.title, description=r.description, quote=line, priority=r.priority, vague=r.vague))
        return UpdateOut(ops=ops)
    return _call(UpdateOut, "extractor", prompts.UPDATER, f"CURRENT REQUIREMENTS:\n{cur}\n\nNEW TRANSCRIPT:\n{transcript[:30_000]}", mock)

# ---------------------------------------------------------------- 2. Clarifier (senior consultant questions)
def clarify(reqs: list[Requirement]) -> list[Question]:
    body = "\n".join(f"{r.id} [{r.priority}{', VAGUE' if r.vague else ''}]: {r.title} — {r.description}" for r in reqs)
    def mock() -> ClarifyOut:
        return ClarifyOut(questions=[Question(requirement_id=r.id, text=f"What exactly should '{r.title}' do, and how will we know it is done?",
                                               why="The request is vague, so the hours could swing a lot.") for r in reqs if r.vague][:6])
    return _call(ClarifyOut, "clarifier", prompts.CLARIFIER, f"REQUIREMENTS:\n{body}", mock, 1200).questions

# ---------------------------------------------------------------- 3. Brain checker (talks to Task 1 over HTTP)
def check_with_brain(brain: BrainClient, reqs: list[Requirement]) -> list[Finding]:
    def one(r: Requirement) -> Finding:
        q = f"Can this client need be met with an existing product setting or feature, without custom code? Need: {r.title}. {r.description}"
        try:
            a = brain.ask(q)
        except Exception as e:                      # brain down -> say so honestly; estimator treats it as custom
            return Finding(requirement_id=r.id, solvable_by_setting=False, note=f"Knowledge Brain unavailable ({type(e).__name__}); assumed custom work.")
        ok = bool(a.get("answered")) and a.get("confidence", 0) >= 0.6
        return Finding(requirement_id=r.id, solvable_by_setting=ok, sources=[s["url"] for s in a.get("sources", [])],
                       note=(a.get("answer") or "")[:400] if ok else "No supporting help-center article found; assumed custom work.")
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(one, reqs))

# ---------------------------------------------------------------- 4. Estimator
def estimate(reqs: list[Requirement], findings: list[Finding], calibration: dict[str, float], feedback: list[str] | None = None) -> list[Task]:
    fmap = {f.requirement_id: f for f in findings}
    body = "\n".join(f"{r.id} [{r.priority}{', VAGUE' if r.vague else ''}]: {r.title} — {r.description}\n   FINDING: "
                     f"{'solvable by existing setting — ' + fmap[r.id].note if r.id in fmap and fmap[r.id].solvable_by_setting else 'no existing setting found'}" for r in reqs)
    cal = "\n".join(f"- {k}: past actuals were {v:.2f}x the estimate midpoint" for k, v in calibration.items()) or "(no history yet)"
    fb = ("\nREVIEWER ISSUES TO FIX:\n" + "\n".join(f"- {i}" for i in feedback)) if feedback else ""
    def mock() -> EstimateOut:
        out = []
        for r in reqs:
            f = fmap.get(r.id)
            if f and f.solvable_by_setting:
                out.append(TaskIn(title=f"Configure: {r.title}", requirement_ids=[r.id], kind="config", basis="existing_setting",
                                  hours_low=0.5, hours_high=1.5, assumptions=["Uses an existing product setting: " + f.note[:80]]))
            else:
                lo, hi = (12, 28) if r.vague else (6, 12)
                out.append(TaskIn(title=f"Build: {r.title}", requirement_ids=[r.id], kind="other", basis="custom", hours_low=lo, hours_high=hi,
                                  assumptions=["Vague request: range is wide until clarified."] if r.vague else []))
        return EstimateOut(tasks=out)
    res = _call(EstimateOut, "estimator", prompts.ESTIMATOR, f"REQUIREMENTS AND FINDINGS:\n{body}\n\nCALIBRATION:\n{cal}{fb}", mock)
    return [Task(id=f"T{i+1}", **{**t.model_dump(), "hours_high": max(t.hours_high, t.hours_low)}) for i, t in enumerate(res.tasks)]

# ---------------------------------------------------------------- 5. Reviewer = deterministic checks + LLM second opinion
def validate(scope: Scope) -> list[str]:
    issues = []
    live = {r.id for r in scope.requirements if r.status != "removed"}
    covered = {rid for t in scope.tasks for rid in t.requirement_ids}
    issues += [f"Requirement {r} has no task." for r in sorted(live - covered)]
    issues += [f"Task {t.id} references unknown requirement {rid}." for t in scope.tasks for rid in t.requirement_ids if rid not in live]
    fmap = {f.requirement_id: f for f in scope.findings}
    for t in scope.tasks:
        if t.basis == "existing_setting" and not all(fmap.get(r) and fmap[r].solvable_by_setting for r in t.requirement_ids):
            issues.append(f"Task {t.id} claims an existing setting but the Knowledge Brain did not confirm one.")
        if t.hours_high < t.hours_low: issues.append(f"Task {t.id} has high < low.")
    return issues

def review(scope: Scope) -> list[str]:
    issues = validate(scope)
    body = "\n".join(f"{t.id} ({t.basis}, {t.hours_low}-{t.hours_high}h) covers {t.requirement_ids}: {t.title}. Assumptions: {t.assumptions}" for t in scope.tasks)
    reqs = "\n".join(f"{r.id}: {r.title}{' (VAGUE)' if r.vague else ''}" for r in scope.requirements if r.status != "removed")
    out = _call(ReviewOut, "reviewer", prompts.REVIEWER, f"REQUIREMENTS:\n{reqs}\n\nTASKS:\n{body}",
                lambda: ReviewOut(approved=True, issues=[]), 1000)
    return issues + [i for i in out.issues if i not in issues]

# ---------------------------------------------------------------- 6. Writer
def write_proposal(scope: Scope, price_low: float, price_high: float) -> str:
    lo, hi = scope.total_hours()
    live = [r for r in scope.requirements if r.status != "removed"]
    facts = (f"REQUIREMENTS:\n" + "\n".join(f"- {r.title} (client said: \"{r.quote}\")" for r in live)
             + f"\nOUT OF SCOPE: {scope.out_of_scope}\nQUESTIONS: {[q.text for q in scope.open_questions]}"
             + f"\nTASKS: " + "; ".join(f"{t.title} {t.hours_low}-{t.hours_high}h" for t in scope.tasks)
             + f"\nTOTAL HOURS: {lo}-{hi}\nPRICE: {price_low:.0f}-{price_high:.0f}\nCHANGES: {[c.model_dump() for c in scope.changes]}")
    def mock() -> ProposalOut:
        md = ["# Proposal", "", "## Summary", f"We will deliver {len(live)} items for between {lo:g} and {hi:g} hours (${price_low:,.0f}–${price_high:,.0f}).", ""]
        if scope.changes:
            md += ["## What changed since last time", *[f"- {c.kind.title()}: {c.note}" for c in scope.changes], ""]
        md += ["## What we will do", *[f"- **{r.title}** — you said: “{r.quote}”" for r in live], "",
               "## What is not included", *([f"- {o}" for o in scope.out_of_scope] or ["- Nothing has been ruled out yet."]), "",
               "## Questions we need answered", *([f"- {q.text}" for q in scope.open_questions] or ["- None right now."]), "",
               "## Time and cost", *[f"- {t.title}: {t.hours_low:g}–{t.hours_high:g} h" for t in scope.tasks], "", "## Next step", "Reply to approve, or tell us what to change."]
        return ProposalOut(markdown="\n".join(md))
    return _call(ProposalOut, "writer", prompts.WRITER, facts, mock, 3000).markdown
