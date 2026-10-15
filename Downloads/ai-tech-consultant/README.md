# AI Tech Consultant

One system, three connected tasks. Tasks 2 and 3 use Task 1 **only through its HTTP API**.

| Folder | What it is | Language | Port |
|---|---|---|---|
| `knowledge_brain/` | Reads the Brilliant Directories help center, understands screenshots, stays fresh daily, answers with sources, escalates to a human when unsure | Python (FastAPI) | 8001 |
| `inbox_agent/` | Reads customer email, asks the Brain for facts, drafts a reply, learns from human edits, earns auto-send per email type | TypeScript (strict, Express) | 8002 |
| `scope_agent/` | Team of 5 agents: meeting transcript → scope, hour estimates, proposal; follow-up meetings update the scope | Python (FastAPI) | 8003 |

## Run it
```bash
cp .env.example .env        # add ANTHROPIC_API_KEY
make up                     # starts all three
make first-sync             # first full read of the help center (polite, resumable)
```
Try it: `curl -X POST localhost:8001/ask -H 'content-type: application/json' -d '{"question":"How do refunds work?"}'`
API docs: http://localhost:8001/docs and http://localhost:8003/docs.

## Test (no API key needed)
`make test` runs 22 offline tests with a mock model. `make evals` runs the live evals (needs a key).

## Read next
`DESIGN.md` (why and how) · `EVALS.md` (numbers) · `AI_LOG.md` (how AI was used)
