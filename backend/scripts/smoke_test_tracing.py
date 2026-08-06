"""Manual smoke-test: make real traced calls and check they reach Langfuse (LEG-83).

Unlike tests/test_observability.py, which fakes the Langfuse client, this uses
the real SDK against a real instance and the real company API. It is the only
way to find out whether what we send is something Langfuse actually accepts —
a fake can only ever confirm we call our own fake correctly.

Usage, from backend/:
    uv run python scripts/smoke_test_tracing.py

Requires COMPANY_API_URL/COMPANY_API_KEY and the three LANGFUSE_* variables in
backend/.env, plus a Langfuse running at LANGFUSE_BASE_URL:
    docker compose -f docker-compose.langfuse.yml up -d   # from the repo root
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from embeddings.company_api import CompanyEmbeddingProvider  # noqa: E402
from observability import build_tracer  # noqa: E402
from observability.tracer import NullTracer  # noqa: E402
from services.company_llm import CompanyLLMProvider  # noqa: E402

ARABIC_QUESTION = "ما هي مدة الإجازة السنوية للعامل؟"
ENGLISH_PROMPT = "Reply with exactly one short sentence: what is annual leave?"


def main() -> int:
    tracer = build_tracer()
    print(f"tracer: {type(tracer).__name__}")

    if isinstance(tracer, NullTracer):
        print(
            "\nTracing is off, so there would be nothing to look at.\n"
            "Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL\n"
            "in backend/.env and run this again. (A NullTracer is correct\n"
            "behaviour, not a bug - it is exactly what CI gets.)"
        )
        return 1

    print("\n--- embedding call (Arabic input) ---")
    embeddings = CompanyEmbeddingProvider(tracer=tracer)
    vectors = embeddings.embed([ARABIC_QUESTION])
    width = len(vectors[0]) if vectors else 0
    print(f"model: {embeddings.model}")
    print(f"got {len(vectors)} vector(s), {width} wide")

    print("\n--- llm call ---")
    llm = CompanyLLMProvider(tracer=tracer)
    reply = llm.generate(ENGLISH_PROMPT)
    print(f"model: {llm.model}")
    print(f"reply: {reply}")

    # Nothing has necessarily left this process yet. The SDK batches in a
    # background thread, and a script exits long before that thread would send.
    tracer.flush()
    print("\nflushed - open the Langfuse UI and look under Tracing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
