"""Manual smoke-test: make real traced calls and check they reach Langfuse.

Two parts, and the difference between them is the point:

  LEG-83 - two providers called directly, producing two separate top-level
           traces. This is what tracing looked like before nesting.
  LEG-84 - a full RagService.ask() run, producing ONE `rag-run` trace with
           those same calls nested underneath it.

Unlike tests/test_observability.py, which fakes the Langfuse client, this uses
the real SDK against a real instance and the real company API. It is the only
way to find out whether what we send is something Langfuse actually accepts —
a fake can only ever confirm we call our own fake correctly.

No database is involved. CaseReader and ChunkSearcher are Protocols, so plain
fakes satisfy them, and the graph, the retrieval service and the answer service
are all the real ones.

Usage, from backend/:
    uv run python scripts/smoke_test_tracing.py

Requires COMPANY_API_URL/COMPANY_API_KEY and the three LANGFUSE_* variables in
backend/.env, plus a Langfuse running at LANGFUSE_BASE_URL:
    docker compose -f docker-compose.langfuse.yml up -d   # from the repo root
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from embeddings.company_api import CompanyEmbeddingProvider  # noqa: E402
from foundation.authorization import AllCases, AuthorizedCases  # noqa: E402
from foundation.models import DocumentChunk, Role, User  # noqa: E402
from observability import build_tracer  # noqa: E402
from observability.tracer import NullTracer, Tracer  # noqa: E402
from services.answer_service import AnswerService  # noqa: E402
from services.company_llm import CompanyLLMProvider  # noqa: E402
from services.rag_service import RagService  # noqa: E402
from services.retrieval_service import RetrievalService  # noqa: E402

ARABIC_QUESTION = "ما هي مدة الإجازة السنوية للعامل؟"
ENGLISH_PROMPT = "Reply with exactly one short sentence: what is annual leave?"

# Fixture text, paraphrased from the labour law, not a legal source.
PASSAGES = [
    "يستحق العامل عن كل عام إجازة سنوية مدتها لا تقل عن واحد وعشرين يوماً، "
    "تزاد إلى مدة لا تقل عن ثلاثين يوماً إذا أمضى العامل في خدمة صاحب العمل "
    "خمس سنوات متصلة.",
    "للعامل أن يتقدم بطلب لتأجيل إجازته السنوية أو أيام منها إلى العام التالي بموافقة صاحب العمل.",
]


class FakeCaseReader:
    """Every case is in scope. Authorisation is not what this script tests."""

    def authorized_cases(self, user: User) -> AuthorizedCases:
        return AllCases()


class FakeChunkSearcher:
    """Returns the fixture passages instead of running a vector query."""

    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = chunks

    def search(
        self,
        query_vector: list[float],
        within: AuthorizedCases,
        limit: int,
    ) -> list[DocumentChunk]:
        return self._chunks[:limit]

    def get_by_document(self, document_id: int) -> list[DocumentChunk]:
        return [c for c in self._chunks if c.document_id == document_id]


@dataclass
class FakeDocument:
    filename: str


class FakeDocumentRepository:
    """Only `_filename` uses this, and only to turn an id into a name."""

    def get_by_id(self, document_id: int) -> FakeDocument:
        return FakeDocument(filename="labour-law.pdf")


def fixture_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            id=index + 1,
            case_id=1,
            document_id=1,
            page_number=index + 1,
            sequence=index,
            text=text,
        )
        for index, text in enumerate(PASSAGES)
    ]


def direct_provider_calls(tracer: Tracer) -> None:
    """LEG-83: each call is its own top-level trace."""
    print("\n=== LEG-83: direct provider calls ===")

    embeddings = CompanyEmbeddingProvider(tracer=tracer)
    vectors = embeddings.embed([ARABIC_QUESTION])
    width = len(vectors[0]) if vectors else 0
    print(f"embedding: {embeddings.model}, {len(vectors)} vector(s), {width} wide")

    llm = CompanyLLMProvider(tracer=tracer)
    reply = llm.generate(ENGLISH_PROMPT)
    print(f"llm: {llm.model}")
    print(f"reply: {reply}")


def full_rag_run(tracer: Tracer) -> None:
    """LEG-84: one `rag-run` trace with the provider calls nested inside it."""
    print("\n=== LEG-84: full RagService.ask() ===")

    llm = CompanyLLMProvider(tracer=tracer)
    service = RagService(
        case_reader=FakeCaseReader(),
        retrieval=RetrievalService(
            chunks=FakeChunkSearcher(fixture_chunks()),
            embedding_provider=CompanyEmbeddingProvider(tracer=tracer),
        ),
        answers=AnswerService(llm),
        documents=FakeDocumentRepository(),
        llm=llm,
        tracer=tracer,
    )

    user = User(
        id=1,
        email="smoke@example.com",
        full_name="Smoke Test",
        hashed_password="not-a-real-hash",
        role=Role.PARTNER,
    )

    response = service.ask(ARABIC_QUESTION, user)

    print(f"answered: {response.answer is not None}")
    print(f"answer: {response.answer}")
    for citation in response.citations:
        print(f"  cited: {citation.document_name} p.{citation.page_number}")


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

    direct_provider_calls(tracer)
    full_rag_run(tracer)

    # Nothing has necessarily left this process yet. The SDK batches in a
    # background thread, and a script exits long before that thread would send.
    tracer.flush()
    print("\nflushed - open the Langfuse UI and look under Tracing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
