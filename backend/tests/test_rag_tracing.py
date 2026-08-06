"""Tests for the run-level span RagService opens (LEG-84).

The nesting itself — provider calls attaching underneath this span — is a
property of the Langfuse SDK and the OpenTelemetry context, and is verified by
scripts/smoke_test_tracing.py against a real instance. What is testable here is
everything we decide: that exactly one span is opened per run, and that it
records what no individual model call could know.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from embeddings.base import EmbeddingProvider, Vector
from foundation.authorization import AllCases, AuthorizedCases, TheseCases
from foundation.models import DocumentChunk, Role, User
from observability.tracer import Kind, Observation, Tracer
from services.answer_service import Answer, AnswerService, Citation
from services.llm import LLMProvider
from services.rag_service import RagService
from services.retrieval_service import RetrievalService


class RecordingTracer(Tracer):
    """Keeps every span opened and the record written back to it."""

    def __init__(self) -> None:
        self.opened: list[dict[str, Any]] = []
        self.records: list[Observation] = []

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        kind: Kind = Kind.SPAN,
        input: Any = None,
        model: str | None = None,
    ) -> Iterator[Observation]:
        self.opened.append({"name": name, "kind": kind, "input": input, "model": model})
        record = Observation()
        self.records.append(record)
        yield record

    def flush(self) -> None:
        return None


class FakeCaseReader:
    def __init__(self, authorized: AuthorizedCases) -> None:
        self._authorized = authorized

    def authorized_cases(self, user: User) -> AuthorizedCases:
        return self._authorized


class FakeEmbeddingProvider(EmbeddingProvider):
    @property
    def dimensions(self) -> int:
        return 4

    def embed(self, texts: list[str]) -> list[Vector]:
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


class FakeChunkSearcher:
    def search(
        self, query_vector: list[float], within: AuthorizedCases, limit: int
    ) -> list[DocumentChunk]:
        return []

    def get_by_document(self, document_id: int) -> list[DocumentChunk]:
        return []


class FakeLLM(LLMProvider):
    def generate(self, prompt: str) -> str:
        return "unused - the graph is replaced in these tests"


class FakeDocumentRepository:
    def get_by_id(self, document_id: int) -> Any:
        class Doc:
            filename = "labour-law.pdf"

        return Doc()


class FakeGraph:
    """Stands in for the compiled graph so a run's shape can be dictated."""

    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.invocations = 0

    def invoke(self, state: Any) -> dict[str, Any]:
        self.invocations += 1
        return self._result


def build_service(
    authorized: AuthorizedCases,
    result: dict[str, Any] | None = None,
) -> tuple[RagService, RecordingTracer, FakeGraph]:
    tracer = RecordingTracer()
    service = RagService(
        case_reader=FakeCaseReader(authorized),
        retrieval=RetrievalService(
            chunks=FakeChunkSearcher(),
            embedding_provider=FakeEmbeddingProvider(),
        ),
        answers=AnswerService(FakeLLM()),
        documents=FakeDocumentRepository(),
        llm=FakeLLM(),
        tracer=tracer,
    )
    graph = FakeGraph(result or {})
    service.graph = graph
    return service, tracer, graph


def a_user() -> User:
    return User(
        id=1,
        email="lawyer@example.com",
        full_name="A Lawyer",
        hashed_password="not-a-real-hash",
        role=Role.PARTNER,
    )


def an_answer() -> dict[str, Any]:
    return {
        "answer": Answer(
            text="Twenty-one days [1].",
            citations=(Citation(document_id=1, page_number=3),),
            answered=True,
        ),
        "citations": (Citation(document_id=1, page_number=3),),
        "route": "single_shot",
        "iterations": 0,
        "matches": [object(), object()],
    }


# --- one span per run ------------------------------------------------------


def test_a_run_opens_exactly_one_span_and_it_is_not_a_model_call() -> None:
    service, tracer, _ = build_service(AllCases(), an_answer())

    service.ask("how long is annual leave?", a_user())

    print(tracer.opened)
    assert len(tracer.opened) == 1
    assert tracer.opened[0]["name"] == "rag-run"
    assert tracer.opened[0]["kind"] == Kind.SPAN
    assert tracer.opened[0]["model"] is None


def test_the_question_is_recorded_as_a_dict_not_a_bare_string() -> None:
    """A bare list or string gets read as chat messages by the UI; a dict
    renders as a labelled row."""
    service, tracer, _ = build_service(AllCases(), an_answer())

    service.ask("how long is annual leave?", a_user())

    print(tracer.opened[0]["input"])
    assert tracer.opened[0]["input"] == {"question": "how long is annual leave?"}


# --- what the span records -------------------------------------------------


def test_a_successful_run_records_the_answer_and_its_citation_count() -> None:
    service, tracer, _ = build_service(AllCases(), an_answer())

    service.ask("how long is annual leave?", a_user())

    print(tracer.records[0].output)
    assert tracer.records[0].output == {
        "answered": True,
        "citations": 1,
        "answer": "Twenty-one days [1].",
    }


def test_the_span_records_what_no_single_model_call_could_know() -> None:
    """Route, passes and passage count exist only at the top of a run."""
    service, tracer, _ = build_service(AllCases(), an_answer())

    service.ask("how long is annual leave?", a_user())

    print(tracer.records[0].metadata)
    assert tracer.records[0].metadata == {
        "scope": "all cases",
        "route": "single_shot",
        "retrieval_passes": 0,
        "passages": 2,
    }


# --- the two kinds of nothing ----------------------------------------------


def test_a_user_authorized_for_nothing_is_recorded_and_never_runs_the_graph() -> None:
    service, tracer, graph = build_service(TheseCases(case_ids=frozenset()))

    response = service.ask("how long is annual leave?", a_user())

    print(f"output={tracer.records[0].output} invocations={graph.invocations}")
    assert response.answer is None
    assert tracer.records[0].output == {"answered": False, "why": "no authorized cases"}
    assert graph.invocations == 0, "no scope means no reason to run anything"


def test_a_run_that_finds_no_grounded_answer_is_recorded_differently() -> None:
    """Both return answer=None to the lawyer. The trace is where the two are
    told apart — one is a permissions problem, the other a retrieval problem."""
    service, tracer, _ = build_service(AllCases(), {"answer": None})

    response = service.ask("how long is annual leave?", a_user())

    print(tracer.records[0].output)
    assert response.answer is None
    assert tracer.records[0].output == {"answered": False, "why": "no grounded answer"}


def test_an_unanswered_answer_object_counts_as_no_answer() -> None:
    result = {"answer": Answer.none_found(), "citations": ()}
    service, tracer, _ = build_service(AllCases(), result)

    service.ask("how long is annual leave?", a_user())

    assert tracer.records[0].output["why"] == "no grounded answer"


# --- scope -----------------------------------------------------------------


def test_scope_counts_the_assigned_cases_rather_than_listing_them() -> None:
    """ "Was this user searching one case or forty" is the useful question; a
    list of integers answers it worse than a count does."""
    service, tracer, _ = build_service(TheseCases(case_ids=frozenset({3, 7, 9})), an_answer())

    service.ask("how long is annual leave?", a_user())

    print(tracer.records[0].metadata["scope"])
    assert tracer.records[0].metadata["scope"] == "3 case(s)"


def test_tracing_off_changes_nothing_about_the_answer() -> None:
    """No tracer passed at all — the default NullTracer must not alter the
    response in any way."""
    service = RagService(
        case_reader=FakeCaseReader(AllCases()),
        retrieval=RetrievalService(
            chunks=FakeChunkSearcher(),
            embedding_provider=FakeEmbeddingProvider(),
        ),
        answers=AnswerService(FakeLLM()),
        documents=FakeDocumentRepository(),
        llm=FakeLLM(),
    )
    service.graph = FakeGraph(an_answer())

    response = service.ask("how long is annual leave?", a_user())

    print(f"answer={response.answer!r} citations={len(response.citations)}")
    assert response.answer == "Twenty-one days [1]."
    assert len(response.citations) == 1
