import json, os, uuid
from pathlib import Path
from . import config
from .models import Proposal, Scope

class Store:
    def __init__(self, root: str | None = None):
        self.root = Path(root or config.DATA_DIR); self.root.mkdir(parents=True, exist_ok=True)
    def _p(self, pid: str) -> Path:
        if not pid.replace("-", "").isalnum(): raise KeyError(pid)       # no path tricks
        return self.root / f"{pid}.json"
    def create(self, name: str) -> str:
        pid = uuid.uuid4().hex[:10]
        self._write(pid, {"name": name, "scopes": [], "proposals": [], "calibration": {}, "actuals": []}); return pid
    def load(self, pid: str) -> dict:
        p = self._p(pid)
        if not p.exists(): raise KeyError(pid)
        return json.loads(p.read_text())
    def _write(self, pid: str, d: dict) -> None:
        tmp = self._p(pid).with_suffix(".tmp"); tmp.write_text(json.dumps(d, indent=1)); os.replace(tmp, self._p(pid))
    def add_version(self, pid: str, scope: Scope, proposal: Proposal) -> None:
        d = self.load(pid); d["scopes"].append(scope.model_dump()); d["proposals"].append(proposal.model_dump()); self._write(pid, d)
    def latest(self, pid: str) -> tuple[Scope, Proposal] | None:
        d = self.load(pid)
        return (Scope(**d["scopes"][-1]), Proposal(**d["proposals"][-1])) if d["scopes"] else None
    def approve(self, pid: str, version: int) -> None:
        d = self.load(pid)
        for p in d["proposals"]:
            if p["version"] == version: p["status"] = "approved"; self._write(pid, d); return
        raise KeyError(version)
    def calibration(self, pid_unused: str | None = None) -> dict[str, float]:
        """Global across projects: median(actual / estimate midpoint) per task kind."""
        ratios: dict[str, list[float]] = {}
        for f in self.root.glob("*.json"):
            for a in json.loads(f.read_text()).get("actuals", []): ratios.setdefault(a["kind"], []).append(a["ratio"])
        return {k: sorted(v)[len(v) // 2] for k, v in ratios.items() if len(v) >= 2}
    def add_actual(self, pid: str, task_id: str, actual_hours: float) -> None:
        d = self.load(pid); scope = Scope(**d["scopes"][-1]); t = next(t for t in scope.tasks if t.id == task_id)
        d["actuals"].append({"task_id": task_id, "kind": t.kind, "actual": actual_hours, "ratio": actual_hours / max((t.hours_low + t.hours_high) / 2, 0.1)}); self._write(pid, d)
