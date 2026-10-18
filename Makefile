PATH := $(CURDIR)/web/node_modules/.bin:$(PATH)
.PHONY: probe-real ui-real-test profile start stop stores voice demo ui-test voice-test types setup test lint eval check-model api web
setup:
	uv sync --group dev
	cd web && pnpm install
api:
	uv run uvicorn app.main:app --app-dir agent --reload --port 8000
web:
	cd web && pnpm dev
test:
	uv run pytest -q
lint:
	uv run ruff check . && uv run ruff format --check .
check-model:
	PYTHONPATH=.:agent uv run python -m app.llm
eval:
	uv run python evals/run_evals.py
types:
	uv run pydantic2ts --module contracts/models.py --output web/lib/contracts.ts
profile:
	./scripts/start_profile.sh
probe-real:
	PYTHONPATH=.:agent uv run python scripts/probe_real.py
ui-real-test:
	uv run --with playwright python scripts/ui_real_e2e.py
start:
	./scripts/start_all.sh
stop:
	./scripts/stop_all.sh
stores:
	PYTHONPATH=. uv run python -m stores.run_all
voice:
	PYTHONPATH=. uv run python -m voice.worker dev
demo:
	PYTHONPATH=. uv run python scripts/demo_cli.py
ui-test:
	uv run --with playwright python scripts/ui_e2e.py
voice-test:
	PYTHONPATH=. uv run python scripts/voice_e2e.py
