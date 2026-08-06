"""Tracing — what the system did, recorded for whoever reads it back later (LEG-83).

Knows nothing about cases, documents or users. It is handed names and payloads
and passes them on.

`LangfuseTracer` is deliberately not exported here. Importing it at package
level would load the Langfuse SDK — and OpenTelemetry behind it — the moment
anything touched this package, which is precisely what factory.py's deferred
import exists to prevent. Whatever genuinely needs the real tracer asks
`build_tracer()` for one.
"""

from observability.factory import build_tracer
from observability.tracer import Kind, NullTracer, Observation, Tracer

__all__ = [
    "Kind",
    "NullTracer",
    "Observation",
    "Tracer",
    "build_tracer",
]
