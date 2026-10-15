import json, pathlib
import httpx, pytest
from app import agents
from app.brain_client import BrainClient
from app.models import Finding, Requirement, Scope, Task
from app.orchestrator import process_meeting
from app.store import Store

T = pathlib.Path(__file__).resolve().parents[1] / "data" / "transcripts"
read = lambda n: (T / n).read_text()

def brain(solvable_words=("colour", "color")):
    def h(req: httpx.Request) -> httpx.Response:
        q = json.loads(req.content)["question"].lower()
        if any(w in q for w in solvable_words):
            return httpx.Response(200, json={"answered": True, "answer": "Open Design Settings and pick a colour.", "sources": [{"url": "https://kb/theme", "title": "Theme"}], "confidence": 0.9, "task_id": None})
        return httpx.Response(200, json={"answered": False, "answer": "I don't know", "sources": [], "confidence": 0, "task_id": 1})
    return BrainClient("http://brain.test", "", transport=httpx.MockTransport(h), retries=0)

def test_first_meeting_builds_scope_with_findings_and_tasks(tmp_path):
    st = Store(str(tmp_path)); pid = st.create("bakery")
    scope, prop = process_meeting(st, brain(), pid, [read("t1_bakery_kickoff.txt")])
    titles = [r.title.lower() for r in scope.requirements]
    assert any("online ordering" in t for t in titles) and any("newsletter" in t for t in titles)
    assert scope.out_of_scope, "client said no mobile app"
    colour = next(r for r in scope.requirements if "colour" in r.description)
    task = next(t for t in scope.tasks if colour.id in t.requirement_ids)
    assert task.basis == "existing_setting" and task.hours_high <= 2          # setting found via Brain -> cheap
    assert all(any(r.id in t.requirement_ids for t in scope.tasks) for r in scope.requirements)   # full coverage
    assert prop.status == "draft" and prop.price_high >= prop.price_low

def test_followup_updates_scope_instead_of_starting_over(tmp_path):
    st = Store(str(tmp_path)); pid = st.create("bakery")
    s1, _ = process_meeting(st, brain(), pid, [read("t1_bakery_kickoff.txt")])
    s2, p2 = process_meeting(st, brain(), pid, [read("t2_bakery_followup.txt")])
    assert s2.version == 2
    newsletter = next(r for r in s2.requirements if "newsletter" in r.title.lower())
    assert newsletter.status == "removed"
    assert not any(newsletter.id in t.requirement_ids for t in s2.tasks)         # its work is no longer quoted
    kinds = {c.kind for c in s2.changes}
    assert {"removed", "added"} <= kinds
    unchanged_before = {t.title for t in s1.tasks if any(r.id != newsletter.id and r.status == "unchanged" for r in s2.requirements if r.id in t.requirement_ids)}
    assert unchanged_before & {t.title for t in s2.tasks}                          # untouched tasks survive
    assert "What changed since last time" in p2.markdown

def test_reviewer_catches_uncovered_requirement_and_fake_setting_claims():
    reqs = [Requirement(id="R1", title="a", description="a"), Requirement(id="R2", title="b", description="b")]
    scope = Scope(project_id="p", version=1, requirements=reqs,
                  findings=[Finding(requirement_id="R1", solvable_by_setting=False, note="")],
                  tasks=[Task(id="T1", requirement_ids=["R1"], title="x", kind="config", basis="existing_setting", hours_low=1, hours_high=1)])
    issues = agents.validate(scope)
    assert any("R2" in i and "no task" in i for i in issues)
    assert any("claims an existing setting" in i for i in issues)

def test_brain_outage_degrades_to_custom_work_not_a_crash(tmp_path):
    down = BrainClient("http://x.test", "", transport=httpx.MockTransport(lambda r: httpx.Response(500)), retries=0)
    st = Store(str(tmp_path)); pid = st.create("g")
    scope, _ = process_meeting(st, down, pid, [read("t3_gym_kickoff.txt")])
    assert scope.tasks and all(t.basis == "custom" for t in scope.tasks)
    assert any("unavailable" in f.note for f in scope.findings)

def test_vague_requirement_gets_clarifying_question_and_wide_range(tmp_path):
    st = Store(str(tmp_path)); pid = st.create("g")
    scope, _ = process_meeting(st, brain(), pid, [read("t3_gym_kickoff.txt")])
    vague = next(r for r in scope.requirements if "search" in r.description)
    assert vague.vague and any(q.requirement_id == vague.id for q in scope.open_questions)

def test_calibration_learns_from_actual_hours(tmp_path):
    st = Store(str(tmp_path)); pid = st.create("g")
    scope, _ = process_meeting(st, brain(), pid, [read("t3_gym_kickoff.txt")])
    for t in scope.tasks[:2]: st.add_actual(pid, t.id, (t.hours_low + t.hours_high))   # actual = 2x midpoint
    assert all(v > 1.5 for v in st.calibration().values())

def test_store_rejects_path_tricks(tmp_path):
    with pytest.raises(KeyError): Store(str(tmp_path)).load("../../etc/passwd")
