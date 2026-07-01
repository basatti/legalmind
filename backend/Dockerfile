FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN pip install uv && uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
