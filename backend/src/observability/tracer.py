"""The tracing interface (LEG-83).

Everything that wants to be observed depends on `Tracer`, never on Langfuse.
Same reasoning as `LLMProvider` in services/llm.py: a vendor SDK is a moving
target, and code scattered with `langfuse.start_as_current_observation(...)`
would have to be rewritten every time that SDK changes shape. Here it changes
in one file, langfuse_tracer.py.

The second reason is `NullTracer`. Tracing has to disappear completely when
nothing is configured — CI has no Langfuse credentials, and a hard dependency
on them would break the build exactly the way ba1f29a had to fix for the model
providers. An interface with a do-nothing implementation makes "unconfigured"
an ordinary case rather than a special one: no `if tracing_enabled` branches at
any call site.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    """What sort of work is being observed.

    These are the three of Langfuse's observation types this project has a use
    for, named here so no call site has to import Langfuse's own literals. A
    generation is a text completion, an embedding is a vectorisation, and a
    span is anything else — including the whole-run wrapper LEG-84 will add.
    """

    SPAN = "span"
    GENERATION = "generation"
    EMBEDDING = "embedding"


@dataclass
class Observation:
    """One unit of observed work, filled in as it happens.

    Mutable, and handed to the caller rather than returned at the end, because
    the interesting fields are only known once the work is done: a provider
    sets `output` after the model has replied. The tracer reads it when the
    block closes.
    """

    output: Any = None
    """Whatever the work produced. Set by the caller before the block exits."""

    usage: dict[str, int] = field(default_factory=dict)
    """Token counts, when the provider reports them. Keys follow Langfuse's own
    vocabulary — `input`, `output`, `total` — so they pass straight through
    without a translation table. Left empty when the API returns no usage
    block, which is not an error: a count nobody reported is absent, not zero."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Anything else worth seeing that is neither the input nor the output —
    how many texts were embedded, which model answered."""

    trace_id: str | None = None
    """Which trace this observation ended up in. The one field written by the
    *tracer* and read by the caller, rather than the other way round: it only
    exists once a span is open, and a caller cannot know it in advance. Needed
    to score a run after it has finished (LEG-87) — RAGAS grades a whole batch
    once every item has been answered, by which time the spans are closed.
    None under `NullTracer`, and under any failure to open a span."""


class Tracer(ABC):
    """Records what the system did, for someone reading it back later."""

    @abstractmethod
    def observe(
        self,
        name: str,
        *,
        kind: Kind = Kind.SPAN,
        input: Any = None,
        model: str | None = None,
    ) -> AbstractContextManager[Observation]:
        """Observe the work done inside the `with` block.

        Latency is not a parameter: it is the duration of the block, which the
        implementation measures itself. Asking every call site to time its own
        work would be one more thing to get wrong, and to get wrong
        inconsistently.
        """

    @abstractmethod
    def score(
        self,
        name: str,
        value: float,
        *,
        comment: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Attach a numeric score to observed work.

        Separate from `Observation` on purpose. Everything on that record is
        something the observed work itself produced — its output, its tokens.
        A score is a *judgement about* that work, arrived at afterwards and by
        someone else: the eval harness deciding whether the answer was right
        (LEG-87). Folding it into the record would blur who said what.

        Two timings, because judgements arrive at two different moments. With
        no `trace_id` the score lands on whatever span is currently open, which
        is what a check made on the spot wants. With one — taken from
        `Observation.trace_id` while the span was open — it lands on that
        trace however long afterwards, which is what a batch grader needs.
        """

    @abstractmethod
    def flush(self) -> None:
        """Send anything still buffered.

        Needed because the SDK batches in a background thread, so a short-lived
        process — the eval harness in LEG-86, a one-off script — can exit with
        traces still unsent. A long-running process like the API never needs it.
        """


class NullTracer(Tracer):
    """Records nothing. What you get when Langfuse is not configured.

    Deliberately not a stub that raises. This is the normal state in CI and on
    any machine that has not set the keys, and the system must behave
    identically with it in place, apart from producing no traces.
    """

    @contextmanager
    def _nothing(self) -> Iterator[Observation]:
        yield Observation()

    def observe(
        self,
        name: str,
        *,
        kind: Kind = Kind.SPAN,
        input: Any = None,
        model: str | None = None,
    ) -> AbstractContextManager[Observation]:
        # An Observation is still handed out and still written to. Callers have
        # no branch for "tracing off"; their writes simply go nowhere.
        return self._nothing()

    def score(
        self,
        name: str,
        value: float,
        *,
        comment: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        return None

    def flush(self) -> None:
        return None
