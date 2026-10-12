.PHONY: install run test lint

install:
	uv sync

run:
	uv run uvicorn my_finance_ai.main:create_app --factory --reload --port 8000

test:
	uv run pytest -n auto

lint:
	uv run pre-commit run --all-files
