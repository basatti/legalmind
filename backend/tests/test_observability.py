"""Tests for the tracing package (LEG-83).

No Langfuse server and no keys. A fake client stands in for the SDK, so these
check the two things that are actually this package's job: that the right thing
gets recorded, and that a broken trace server can never break a request.
"""

from typing import Any

import pytest

from observability import build_tracer
from observability.langfuse_tracer import LangfuseTracer
from observability.tracer import Kind, NullTracer


class FakeSpan:
    """Stands in for a LangfuseSpan/LangfuseGeneration."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeManager:
    def __init__(self, span: FakeSpan) -> None:
        self.span = span

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(self, *exc: Any) -> bool:
        return False


class FakeClient:
    """Records what the tracer asked the SDK to do."""

    def __init__(self) -> None:
        self.opened: list[dict[str, Any]] = []
        self.span = FakeSpan()
        self.flushes = 0
        self.scores: list[dict[str, Any]] = []

    def start_as_current_observation(self, **kwargs: Any) -> FakeManager:
        self.opened.append(kwargs)
        return FakeManager(self.span)

    def get_current_trace_id(self) -> str:
        return "trace-abc123"

    def score_current_span(self, **kwargs: Any) -> None:
        self.scores.append({**kwargs, "via": "current_span"})

    def create_score(self, **kwargs: Any) -> None:
        self.scores.append({**kwargs, "via": "create_score"})

    def flush(self) -> None:
        self.flushes += 1


def traced() -> tuple[LangfuseTracer, FakeClient]:
    client = FakeClient()
    return LangfuseTracer(client), client  # type: ignore[arg-type]


# --- the null tracer -------------------------------------------------------


def test_the_null_tracer_still_hands_out_a_record_to_write_to() -> None:
    """The whole point: callers have no branch for "tracing is off"."""
    tracer = NullTracer()

    with tracer.observe("anything", kind=Kind.GENERATION) as record:
        record.output = "a reply"
        record.usage = {"input": 10}

    print(f"output={record.output!r} usage={record.usage}")
    assert record.output == "a reply"


def test_the_null_tracer_flushes_without_complaint() -> None:
    assert NullTracer().flush() is None


# --- what reaches the SDK --------------------------------------------------


def test_a_generation_records_the_prompt_reply_model_and_tokens() -> None:
    tracer, client = traced()

    with tracer.observe("company-llm", kind=Kind.GENERATION, input="q?", model="gpt-oss") as record:
        record.output = "an answer"
        record.usage = {"input": 812, "output": 96}

    print(f"opened={client.opened}")
    print(f"updates={client.span.updates}")
    assert client.opened[0]["as_type"] == "generation"
    assert client.opened[0]["input"] == "q?"
    assert client.opened[0]["model"] == "gpt-oss"
    assert client.span.updates[0]["output"] == "an answer"
    assert client.span.updates[0]["usage_details"] == {"input": 812, "output": 96}


def test_an_embedding_opens_an_embedding_not_a_generation() -> None:
    tracer, client = traced()

    with tracer.observe("company-embeddings", kind=Kind.EMBEDDING, model="bge-m3"):
        pass

    print(client.opened[0])
    assert client.opened[0]["as_type"] == "embedding"


def test_a_plain_span_is_never_given_a_model() -> None:
    """The SDK's span variant has no `model` parameter — a span is not a model
    call. Passing one anyway is what mypy caught during LEG-83."""
    tracer, client = traced()

    with tracer.observe("rag-run", kind=Kind.SPAN, input="q?", model="gpt-oss"):
        pass

    print(client.opened[0])
    assert client.opened[0]["as_type"] == "span"
    assert "model" not in client.opened[0]


def test_unreported_tokens_are_sent_as_nothing_rather_than_an_empty_block() -> None:
    """A count nobody reported is absent, not zero."""
    tracer, client = traced()

    with tracer.observe("company-llm", kind=Kind.GENERATION) as record:
        record.output = "an answer"

    print(client.span.updates[0])
    assert client.span.updates[0]["usage_details"] is None
    assert client.span.updates[0]["metadata"] is None


# --- tracing must never break the request ----------------------------------


def test_a_client_that_cannot_open_a_span_does_not_break_the_caller() -> None:
    class Broken:
        def start_as_current_observation(self, **kwargs: Any) -> Any:
            raise RuntimeError("langfuse is down")

    tracer = LangfuseTracer(Broken())  # type: ignore[arg-type]

    with tracer.observe("company-llm", kind=Kind.GENERATION) as record:
        record.output = "the answer still happened"

    print(f"survived, output={record.output!r}")
    assert record.output == "the answer still happened"


def test_a_client_that_cannot_write_back_does_not_break_the_caller() -> None:
    class BrokenSpan:
        def update(self, **kwargs: Any) -> None:
            raise RuntimeError("langfuse fell over mid-write")

    class BrokenClient:
        def start_as_current_observation(self, **kwargs: Any) -> Any:
            return FakeManager(BrokenSpan())  # type: ignore[arg-type]

    tracer = LangfuseTracer(BrokenClient())  # type: ignore[arg-type]

    with tracer.observe("company-llm", kind=Kind.GENERATION) as record:
        record.output = "still fine"

    print(f"survived, output={record.output!r}")
    assert record.output == "still fine"


def test_a_failure_in_the_observed_work_is_never_swallowed() -> None:
    """The opposite rule: our failures are hidden, the caller's never are.
    Swallowing an LLMError here would turn an outage into "no answer found"."""
    tracer, client = traced()

    with (
        pytest.raises(ValueError, match="the model exploded"),
        tracer.observe("company-llm", kind=Kind.GENERATION),
    ):
        raise ValueError("the model exploded")

    print(f"span still closed: {client.span.updates}")
    assert client.span.updates, "the span must still be written back on failure"


def test_flush_reaches_the_client_and_survives_it_failing() -> None:
    tracer, client = traced()
    tracer.flush()
    assert client.flushes == 1

    class BrokenFlush:
        def flush(self) -> None:
            raise RuntimeError("nope")

    LangfuseTracer(BrokenFlush()).flush()  # type: ignore[arg-type]


# --- scores (LEG-87) -------------------------------------------------------


def test_a_score_with_no_trace_id_lands_on_the_open_span() -> None:
    tracer, client = traced()

    with tracer.observe("gold-item", kind=Kind.SPAN):
        tracer.score("answer_hit", 1.0, comment="matched 'واحد وعشرين'")

    print(f"scores={client.scores}")
    assert client.scores == [
        {
            "name": "answer_hit",
            "value": 1.0,
            "comment": "matched 'واحد وعشرين'",
            "via": "current_span",
        }
    ]


def test_a_span_reports_the_trace_it_landed_in() -> None:
    """What lets a batch grader come back to an item after its span has closed."""
    tracer, _ = traced()

    with tracer.observe("gold-item", kind=Kind.SPAN) as record:
        pass

    assert record.trace_id == "trace-abc123"


def test_a_score_with_a_trace_id_is_created_against_that_trace() -> None:
    """RAGAS grades the whole batch once every span is closed (LEG-87)."""
    tracer, client = traced()

    with tracer.observe("gold-item", kind=Kind.SPAN) as record:
        pass

    tracer.score("faithfulness", 0.83, trace_id=record.trace_id)

    print(f"scores={client.scores}")
    assert client.scores == [
        {
            "name": "faithfulness",
            "value": 0.83,
            "comment": None,
            "trace_id": "trace-abc123",
            "via": "create_score",
        }
    ]


def test_the_null_tracer_reports_no_trace_id_to_score_against() -> None:
    """Untraced runs must not silently look like they were scored."""
    with NullTracer().observe("gold-item") as record:
        pass

    assert record.trace_id is None


def test_a_score_that_cannot_be_recorded_does_not_break_the_caller() -> None:
    """Same rule as everywhere else here: a broken trace server is never fatal.

    An eval run that dies because Langfuse rejected a score would lose the
    whole measurement, which costs far more than the missing score.
    """

    class BrokenScore:
        def score_current_span(self, **kwargs: Any) -> None:
            raise RuntimeError("score rejected")

        def create_score(self, **kwargs: Any) -> None:
            raise RuntimeError("score rejected")

    broken = LangfuseTracer(BrokenScore())  # type: ignore[arg-type]
    broken.score("answer_hit", 1.0)
    broken.score("faithfulness", 0.5, trace_id="trace-abc123")


def test_a_client_that_will_not_report_a_trace_id_does_not_break_the_caller() -> None:
    class NoTraceId:
        def start_as_current_observation(self, **kwargs: Any) -> FakeManager:
            return FakeManager(FakeSpan())

        def get_current_trace_id(self) -> str:
            raise RuntimeError("no context")

    with LangfuseTracer(NoTraceId()).observe("gold-item") as record:  # type: ignore[arg-type]
        pass

    assert record.trace_id is None


def test_the_null_tracer_accepts_a_score_and_discards_it() -> None:
    assert NullTracer().score("answer_hit", 1.0) is None


# --- choosing a tracer from config -----------------------------------------


def clear_langfuse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_no_keys_means_no_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_langfuse_env(monkeypatch)

    tracer = build_tracer()

    print(f"got {type(tracer).__name__}")
    assert isinstance(tracer, NullTracer)


def test_half_the_keys_still_means_no_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_langfuse_env(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    assert isinstance(build_tracer(), NullTracer)


def test_keys_without_a_base_url_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The important one. Left to itself the SDK defaults to cloud.langfuse.com,
    and traced prompts carry verbatim case-document text. A half-configured
    install must not quietly become an export of client material."""
    clear_langfuse_env(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    tracer = build_tracer()

    print(f"got {type(tracer).__name__}")
    assert isinstance(tracer, NullTracer)


def test_a_full_local_configuration_gives_a_real_tracer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_langfuse_env(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    tracer = build_tracer()

    print(f"got {type(tracer).__name__}")
    assert isinstance(tracer, LangfuseTracer)
