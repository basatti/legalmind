"""The real tracer, backed by Langfuse (LEG-83).

The only module in the project that imports Langfuse. Everything else depends
on `Tracer` — see tracer.py for why.

Nothing here may break a request. Observability is a convenience for whoever
debugs this later; the lawyer waiting on an answer does not care that the trace
server is down. So every call into the SDK is guarded, and a failure is logged
and swallowed rather than raised. Exceptions from the *observed* work are never
touched: they propagate exactly as they would without tracing, and Langfuse
marks the span failed on its way past.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse

from observability.tracer import Kind, Observation, Tracer

logger = logging.getLogger(__name__)


class LangfuseTracer(Tracer):
    """Sends observations to a Langfuse instance.

    Takes an already-built client rather than reading the environment itself,
    for the same reason CompanyLLMProvider takes an injected transport: the
    behaviour can then be tested against a fake, with no server and no keys.
    Building the real client from config is factory.py's job.
    """

    def __init__(self, client: Langfuse) -> None:
        self._client = client

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        kind: Kind = Kind.SPAN,
        input: Any = None,
        model: str | None = None,
    ) -> Iterator[Observation]:
        record = Observation()

        try:
            manager = self._start(name, kind, input, model)
        except Exception:
            # Could not even open a span. The work still has to happen, so hand
            # back a record nobody will read and carry on — the same state the
            # caller would be in under NullTracer.
            logger.warning("Langfuse could not open a span for %r", name, exc_info=True)
            yield record
            return

        with manager as span:
            # Read while the span is open — this is the only window in which
            # the SDK knows which trace is current, and LEG-87 needs the id
            # after the block has closed.
            record.trace_id = self._current_trace_id()

            try:
                yield record
            finally:
                # Runs whether the observed work succeeded or raised. On a
                # failure the output is whatever the caller managed to set,
                # which is usually nothing — and a span with no output, sitting
                # inside a failed run, is itself the useful signal.
                self._write_back(span, record, name)

    def _start(self, name: str, kind: Kind, input: Any, model: str | None) -> Any:
        """Open an observation of the right type.

        Branches rather than forwarding `kind.value`, because the SDK overloads
        on a literal `as_type` and the variants genuinely differ: only
        generations and embeddings take a `model`. A plain span is not a model
        call, so it has no model to name.
        """
        if kind is Kind.GENERATION:
            return self._client.start_as_current_observation(
                name=name, as_type="generation", input=input, model=model
            )
        if kind is Kind.EMBEDDING:
            return self._client.start_as_current_observation(
                name=name, as_type="embedding", input=input, model=model
            )
        return self._client.start_as_current_observation(name=name, as_type="span", input=input)

    def _write_back(self, span: Any, record: Observation, name: str) -> None:
        """Copy the finished record onto the span, ignoring any SDK failure."""
        try:
            span.update(
                output=record.output,
                # Empty rather than absent would render as an empty block in
                # the UI, implying the provider reported something it didn't.
                metadata=record.metadata or None,
                usage_details=record.usage or None,
            )
        except Exception:
            logger.warning("Langfuse could not record the result of %r", name, exc_info=True)

    def _current_trace_id(self) -> str | None:
        """The trace the open span belongs to, or None if the SDK won't say."""
        try:
            return self._client.get_current_trace_id()
        except Exception:
            logger.warning("Langfuse could not report the current trace id", exc_info=True)
            return None

    def score(
        self,
        name: str,
        value: float,
        *,
        comment: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Score the open span, or a named trace that has already closed.

        Without an id, `score_current_span` — inside `observe` the span is
        already the active one, so asking the SDK which span that is beats
        making every caller carry it. With an id, `create_score`, which is the
        only route once the span is gone.
        """
        try:
            if trace_id is None:
                self._client.score_current_span(name=name, value=value, comment=comment)
            else:
                self._client.create_score(
                    name=name, value=value, comment=comment, trace_id=trace_id
                )
        except Exception:
            logger.warning("Langfuse could not record score %r", name, exc_info=True)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse could not flush buffered traces", exc_info=True)
