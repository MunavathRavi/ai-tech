"""Single doorway to Claude. Every call is forced through a tool schema, so outputs are structured
JSON, and every call is logged (model, tokens, seconds) so evals can report cost and speed."""
import base64, time
from dataclasses import dataclass, field
from typing import Any, Callable
from . import config

@dataclass
class Ledger:
    calls: list[dict] = field(default_factory=list)
    def add(self, model: str, tin: int, tout: int, secs: float) -> None:
        pin, pout = config.PRICES.get(model, (0.0, 0.0))
        self.calls.append({"model": model, "in": tin, "out": tout, "secs": secs,
                           "usd": (tin * pin + tout * pout) / 1_000_000})
    def total_usd(self) -> float: return sum(c["usd"] for c in self.calls)
    def total_secs(self) -> float: return sum(c["secs"] for c in self.calls)
    def reset(self) -> None: self.calls.clear()

ledger = Ledger()
_client = None

def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client

def structured(system: str, user: str, schema: dict, *, model: str | None = None,
               mock: Callable[[], dict] | None = None, images: list[tuple[str, bytes]] | None = None,
               max_tokens: int = 1500) -> dict[str, Any]:
    """Call Claude and return a dict that matches `schema`. `images` = [(media_type, bytes)]."""
    model = model or config.FAST_MODEL
    if config.LLM_MODE == "mock":
        if mock is None: raise RuntimeError("mock mode needs a mock callable")
        return mock()
    content: list[dict] = []
    for media_type, data in images or []:
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                    "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": user})
    t0 = time.time()
    resp = _get_client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        tools=[{"name": "respond", "description": "Return the structured result.", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "respond"},
        messages=[{"role": "user", "content": content}])
    ledger.add(model, resp.usage.input_tokens, resp.usage.output_tokens, time.time() - t0)
    for block in resp.content:
        if block.type == "tool_use": return dict(block.input)
    raise RuntimeError("model returned no structured output")
