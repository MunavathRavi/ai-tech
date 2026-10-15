from . import agents, config, prompts
from .brain_client import BrainClient
from .models import Change, Finding, Proposal, Requirement, Scope, Task
from .store import Store

MAX_REVIEW_LOOPS = 1

def _price(scope: Scope) -> tuple[float, float]:
    lo, hi = scope.total_hours(); return lo * config.HOURLY_RATE, hi * config.HOURLY_RATE

def _new_scope(pid: str, version: int, reqs: list[Requirement], oos: list[str]) -> Scope:
    return Scope(project_id=pid, version=version, requirements=reqs, out_of_scope=oos,
                 prompt_versions=prompts.VERSIONS, models=dict(config.AGENT_MODELS))

def _next_id(reqs: list[Requirement]) -> str:
    return f"R{1 + max((int(r.id[1:]) for r in reqs), default=0)}"

def _estimate_loop(scope: Scope, targets: list[Requirement], brain: BrainClient, store: Store) -> list[Task]:
    """Check with the Brain, estimate, let the reviewer push back once, keep the findings on the scope."""
    new_findings = agents.check_with_brain(brain, targets)
    scope.findings = [f for f in scope.findings if f.requirement_id not in {t.id for t in targets}] + new_findings
    cal = store.calibration()
    kept = [t for t in scope.tasks if not set(t.requirement_ids) & {r.id for r in targets}]
    fresh = agents.estimate(targets, new_findings, cal)
    issues: list[str] = []
    for loop in range(MAX_REVIEW_LOOPS + 1):
        scope.tasks = kept + fresh
        _renumber(scope)
        issues = agents.review(scope)
        if not issues or loop == MAX_REVIEW_LOOPS: break
        fresh = agents.estimate(targets, new_findings, cal, feedback=issues)
    scope.review_issues = issues                      # unresolved issues are shown to the human, not hidden
    return scope.tasks

def _renumber(scope: Scope) -> None:
    for i, t in enumerate(scope.tasks): t.id = f"T{i+1}"

def process_meeting(store: Store, brain: BrainClient, pid: str, transcripts: list[str]) -> tuple[Scope, Proposal]:
    latest = store.latest(pid)
    if latest is None:                                            # first meeting(s): build the scope
        ex = agents.extract(transcripts)
        reqs = [Requirement(id=f"R{i+1}", title=r.title, description=r.description, quote=r.quote, priority=r.priority, vague=r.vague)
                for i, r in enumerate(ex.requirements)]
        scope = _new_scope(pid, 1, reqs, ex.out_of_scope)
        scope.changes = [Change(kind="added", requirement_id=r.id, note=r.title) for r in reqs]
        scope.open_questions = agents.clarify(reqs) if reqs else []
        if reqs: _estimate_loop(scope, reqs, brain, store)
    else:                                                         # follow-up meeting: UPDATE, do not start over
        prev, _ = latest
        scope = prev.model_copy(deep=True); scope.version = prev.version + 1; scope.changes = []
        scope.prompt_versions, scope.models = prompts.VERSIONS, dict(config.AGENT_MODELS)
        for r in scope.requirements: r.status = "unchanged" if r.status != "removed" else "removed"
        touched: list[Requirement] = []
        for t in transcripts:
            up = agents.update(scope.requirements, t)
            scope.out_of_scope = list(dict.fromkeys(scope.out_of_scope + up.out_of_scope))
            for op in up.ops:
                by_id = {r.id: r for r in scope.requirements}
                if op.action == "add":
                    r = Requirement(id=_next_id(scope.requirements), title=op.title, description=op.description, quote=op.quote,
                                    priority=op.priority, vague=op.vague, status="new")
                    scope.requirements.append(r); touched.append(r); scope.changes.append(Change(kind="added", requirement_id=r.id, note=r.title))
                elif op.action == "change" and op.requirement_id in by_id:
                    r = by_id[op.requirement_id]; r.description = op.description or r.description; r.quote = op.quote or r.quote
                    r.title = op.title or r.title; r.vague = op.vague; r.status = "changed"
                    if r not in touched: touched.append(r)
                    scope.changes.append(Change(kind="changed", requirement_id=r.id, note=op.reason or r.title))
                elif op.action == "remove" and op.requirement_id in by_id:
                    r = by_id[op.requirement_id]; r.status = "removed"; touched = [x for x in touched if x.id != r.id]
                    scope.tasks = [t for t in scope.tasks if r.id not in t.requirement_ids or len(t.requirement_ids) > 1]
                    scope.findings = [f for f in scope.findings if f.requirement_id != r.id]
                    scope.changes.append(Change(kind="removed", requirement_id=r.id, note=op.reason or r.title))
        live = [r for r in scope.requirements if r.status != "removed"]
        scope.open_questions = agents.clarify(live) if live else []
        if touched: _estimate_loop(scope, touched, brain, store)      # only re-estimate what moved
        else: scope.review_issues = agents.review(scope) if scope.tasks else []
    lo, hi = _price(scope)
    prop = Proposal(version=scope.version, markdown=agents.write_proposal(scope, lo, hi), price_low=lo, price_high=hi)
    store.add_version(pid, scope, prop)
    return scope, prop
