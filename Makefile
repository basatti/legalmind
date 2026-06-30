.PHONY: lint format typecheck test check

lint:
	cd backend && uv run ruff check .

format:
	cd backend && uv run ruff format --check .

typecheck:
	cd backend && uv run mypy

test:
	cd backend && uv run pytest

check: lint format typecheck test