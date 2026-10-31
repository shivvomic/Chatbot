# Common tasks. Run `make help` for the list.
PY := .venv/bin/python

.PHONY: help install index api ui test test-llm lint eval eval-fast verify clean

help:  ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Create .venv, install deps, build the index
	scripts/bootstrap.sh

index:  ## Rebuild chunks + vector and BM25 indexes
	$(PY) -m app.retrieval.index --rebuild

api:  ## Run the FastAPI server on :8000
	.venv/bin/uvicorn app.api.main:app --port 8000

ui:  ## Run the Streamlit UI on :8501
	.venv/bin/streamlit run ui/app.py

test:  ## Unit + API tests (LLM tests skip without a key)
	$(PY) -m pytest -q --cov=app --cov-report=term-missing:skip-covered

test-llm:  ## Only the tests that call the real LLM
	$(PY) -m pytest -q -m llm

lint:  ## Ruff
	.venv/bin/ruff check .

eval:  ## Full evaluation (calls the LLM for all 48 questions)
	$(PY) -m eval.run_eval

eval-fast:  ## Retrieval-only evaluation (no LLM)
	$(PY) -m eval.run_eval --fast

verify:  ## Lint, tests, fast eval, start API and probe one question per status
	scripts/verify.sh

clean:  ## Remove caches and generated indexes (data/)
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov data
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
