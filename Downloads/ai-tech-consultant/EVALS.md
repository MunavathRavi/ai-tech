# EVALS

Three eval harnesses, **20 test cases per task**, in `knowledge_brain/evals`, `inbox_agent/evals`, `scope_agent/evals`. Run with `make evals` (needs `ANTHROPIC_API_KEY`). Each prints a markdown table: quality, cost, speed per model. Paste the live tables below.

## What is measured
| Task | Cases | Quality checks | Safety checks |
|---|---|---|---|
| 1 Brain | 20 questions over a 10-article fixture (15 answerable, 3 out-of-knowledge, 1 prompt-injection, 1 gibberish) | expected facts present, citation ⊆ retrieved URLs | must refuse unknowable questions; must ignore injected instruction |
| 2 Inbox | 51 emails, 8 categories | category accuracy; high-risk recall (refund, complaint, quote, injection) | injection never low-risk; autonomy ladder (20 → auto, edit → reset, complaint → revoke) |
| 3 Scope | 15 first meetings + 5 follow-ups | requirement recall, out-of-scope capture, follow-up correctness (removed / changed / added / kept) | every requirement has a task; no unconfirmed "existing setting" claims |

## Offline baselines (measured; no LLM, deterministic)
These are the floor a real model must beat. They also prove the harnesses run.
| Task | Baseline | Result |
|---|---|---|
| 1 | BM25 retrieval, answer = top chunk, no refusal logic beyond "no match" | 17/20 |
| 2 | Keyword classifier | 47/50 category on the original 50-email set, 16/16 high-risk caught |
| 3 | Heuristic extractor / updater | 75/77 checks, 18/20 cases |
Autonomy ladder (Task 2): 20 unchanged → `auto`; 21st email sent without a human. Unit tests cover reset-on-edit, revoke-on-complaint, never-auto categories, and Brain outage.

## Live model comparison — TO FILL (run `make evals`)
Set `FAST_MODEL` / `SMART_MODEL` (and `*_MODEL` per agent in Task 3) to the pair under test and re-run. Suggested decision rule, stated in advance: **choose the cheaper model unless the dearer one is ≥ 5 points better on quality or fixes a safety failure.**

| Task | Model | Quality | $ total | $ / item | s / item |
|---|---|---|---|---|---|
| 1 | claude-haiku-5-5 | | | | |
| 1 | claude-sonnet-5-5 | | | | |
| 2 | claude-haiku-5-5 | | | | |
| 2 | claude-sonnet-5-5 | | | | |
| 3 | haiku extractor / sonnet estimator | | | | |
| 3 | sonnet everywhere | | | | |

Price assumptions live in `config.py` / `llm.ts` (env-overridable); update them to current rates before quoting costs.

## Still to do by hand
- Replace the fixture corpus with 20+ questions written from **real** Brilliant Directories articles, including 3 about screenshot-only answers and 3 about articles that were removed.
- Record 3 real role-played client meetings (samples in `scope_agent/data/transcripts` show the format) and rerun Task 3.
- Test the retries/human-approval behaviour live (stop the Brain mid-run) and note results here.
