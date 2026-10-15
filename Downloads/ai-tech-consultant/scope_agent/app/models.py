from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

Kind = Literal["config", "form", "integration", "page", "report", "other"]
Priority = Literal["must", "should", "could"]

class Requirement(BaseModel):
    id: str
    title: str
    description: str
    quote: str = ""                       # the client's own words, so nothing is invented
    priority: Priority = "should"
    vague: bool = False                   # e.g. "make the search better"
    status: Literal["new", "changed", "unchanged", "removed"] = "new"

class Finding(BaseModel):                 # result of asking the Knowledge Brain (Task 1) about a requirement
    requirement_id: str
    solvable_by_setting: bool
    note: str
    sources: list[str] = []

class Task(BaseModel):
    id: str
    requirement_ids: list[str]
    title: str
    kind: Kind
    basis: Literal["existing_setting", "custom"]
    hours_low: float = Field(ge=0)
    hours_high: float = Field(ge=0)
    assumptions: list[str] = []

class Question(BaseModel):
    requirement_id: str | None = None
    text: str
    why: str

class Change(BaseModel):
    kind: Literal["added", "changed", "removed"]
    requirement_id: str
    note: str

class Scope(BaseModel):
    project_id: str
    version: int
    requirements: list[Requirement]
    out_of_scope: list[str] = []
    open_questions: list[Question] = []
    findings: list[Finding] = []
    tasks: list[Task] = []
    changes: list[Change] = []
    review_issues: list[str] = []
    prompt_versions: dict[str, str] = {}
    models: dict[str, str] = {}
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def total_hours(self) -> tuple[float, float]:
        return (sum(t.hours_low for t in self.tasks), sum(t.hours_high for t in self.tasks))

class Proposal(BaseModel):
    version: int
    markdown: str
    price_low: float
    price_high: float
    status: Literal["draft", "approved"] = "draft"   # human-in-the-loop: nothing is client-ready until approved

# ---- shapes the agents return (also used as the JSON schema sent to Claude) ----
class ReqIn(BaseModel):
    title: str; description: str; quote: str = ""; priority: Priority = "should"; vague: bool = False
class ExtractOut(BaseModel):
    requirements: list[ReqIn]; out_of_scope: list[str] = []
class Op(BaseModel):
    action: Literal["add", "change", "remove", "confirm"]
    requirement_id: str | None = Field(None, description="Existing id for change/remove/confirm; null for add")
    title: str = ""; description: str = ""; quote: str = ""; priority: Priority = "should"; vague: bool = False
    reason: str = ""
class UpdateOut(BaseModel):
    ops: list[Op]; out_of_scope: list[str] = []
class ClarifyOut(BaseModel):
    questions: list[Question]
class TaskIn(BaseModel):
    title: str; requirement_ids: list[str]; kind: Kind; basis: Literal["existing_setting", "custom"]
    hours_low: float = Field(ge=0); hours_high: float = Field(ge=0); assumptions: list[str] = []
class EstimateOut(BaseModel):
    tasks: list[TaskIn]
class ReviewOut(BaseModel):
    approved: bool; issues: list[str]
class ProposalOut(BaseModel):
    markdown: str
