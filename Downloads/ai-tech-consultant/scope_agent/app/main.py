from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .brain_client import BrainClient
from .models import Proposal, Scope
from .orchestrator import process_meeting
from .store import Store

app = FastAPI(title="Meeting to Scope of Work", version="1.0")
store = Store(); brain = BrainClient()

class NewProject(BaseModel): name: str = Field(min_length=1, max_length=120)
class Meeting(BaseModel): transcripts: list[str] = Field(min_length=1, max_length=10)
class Approve(BaseModel): version: int
class Actual(BaseModel): task_id: str; actual_hours: float = Field(gt=0, lt=2000)

def _get(pid: str):
    try: return store.latest(pid)
    except KeyError: raise HTTPException(404, "unknown project")

@app.post("/projects")
def create(b: NewProject): return {"project_id": store.create(b.name)}

@app.post("/projects/{pid}/meetings", response_model=Scope)
def meeting(pid: str, b: Meeting):
    _get(pid)
    if any(len(t) > 60_000 for t in b.transcripts): raise HTTPException(413, "transcript too long")
    return process_meeting(store, brain, pid, b.transcripts)[0]

@app.get("/projects/{pid}/scope", response_model=Scope)
def scope(pid: str):
    r = _get(pid)
    if not r: raise HTTPException(404, "no meetings processed yet")
    return r[0]

@app.get("/projects/{pid}/proposal", response_model=Proposal)
def proposal(pid: str):
    r = _get(pid)
    if not r: raise HTTPException(404, "no meetings processed yet")
    return r[1]

@app.post("/projects/{pid}/approve")
def approve(pid: str, b: Approve):
    _get(pid)
    try: store.approve(pid, b.version)
    except KeyError: raise HTTPException(404, "unknown version")
    return {"ok": True, "note": "Proposal approved by a human; it may now be sent to the client."}

@app.post("/projects/{pid}/actuals")
def actual(pid: str, b: Actual):
    """Feedback loop: real hours teach the estimator (calibration notes in its prompt)."""
    _get(pid)
    try: store.add_actual(pid, b.task_id, b.actual_hours)
    except StopIteration: raise HTTPException(404, "unknown task")
    return {"calibration": store.calibration()}
