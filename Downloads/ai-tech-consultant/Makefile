.PHONY: install test evals up first-sync
install:
	pip install -r knowledge_brain/requirements.txt && cd inbox_agent && npm ci
test:        ## offline, no API key needed
	cd knowledge_brain && python -m pytest -q
	cd scope_agent && python -m pytest -q
	cd inbox_agent && npm run typecheck && npm test
evals:       ## live evals, needs ANTHROPIC_API_KEY; prints markdown tables for EVALS.md
	cd knowledge_brain && python -m evals.run_evals
	cd inbox_agent && npm run evals
	cd scope_agent && python -m evals.run_evals
up:          ## the whole project with ONE command
	docker compose up --build
first-sync:  ## polite first read of the help center (resumable; safe to stop and re-run)
	curl -X POST localhost:8001/sync -H "x-api-key: $$BRAIN_API_KEY"
