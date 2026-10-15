"""Task 3 reaches Task 1 ONLY through its HTTP API (never imports its code)."""
import time
import httpx
from . import config

class BrainClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 transport: httpx.BaseTransport | None = None, retries: int = 2):
        self.http = httpx.Client(base_url=base_url or config.BRAIN_URL, timeout=20, transport=transport,
                                 headers={"x-api-key": api_key if api_key is not None else config.BRAIN_API_KEY})
        self.retries = retries

    def ask(self, question: str) -> dict:
        last: Exception | None = None
        for i in range(self.retries + 1):
            try:
                r = self.http.post("/ask", json={"question": question[:1900], "asker": "scope-agent"})
                r.raise_for_status(); return r.json()
            except httpx.HTTPError as e:
                last = e; time.sleep(0.3 * 2 ** i)
        raise RuntimeError(f"Knowledge Brain unreachable: {last}")
