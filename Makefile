.PHONY: lint format typecheck test check fe-lint

lint:
	cd backend && uv run ruff check .

format:
	cd backend && uv run ruff format --check .

typecheck:
	cd backend && uv run mypy

test:
	cd backend && uv run pytest

fe-lint:
	cd frontend && npm run lint

check: lint format typecheck test fe-lint