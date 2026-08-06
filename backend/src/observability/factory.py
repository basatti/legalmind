"""Chooses which tracer this process gets (LEG-83).

The one place that reads Langfuse config. Everywhere else is handed a `Tracer`
and never asks where it came from.

Unconfigured is the expected case, not a failure: CI has no keys, and neither
does a fresh clone. It returns a NullTracer and logs at info level, because
"tracing is off" is ordinary news.
"""

import logging
import os

from observability.tracer import NullTracer, Tracer

logger = logging.getLogger(__name__)

PUBLIC_KEY = "LANGFUSE_PUBLIC_KEY"
SECRET_KEY = "LANGFUSE_SECRET_KEY"
BASE_URL = "LANGFUSE_BASE_URL"


def build_tracer() -> Tracer:
    """A real tracer if Langfuse is fully configured, a NullTracer otherwise."""
    public_key = os.environ.get(PUBLIC_KEY)
    secret_key = os.environ.get(SECRET_KEY)

    if not public_key or not secret_key:
        logger.info("%s/%s unset - tracing disabled", PUBLIC_KEY, SECRET_KEY)
        return NullTracer()

    base_url = os.environ.get(BASE_URL)
    if not base_url:
        # Refusing on purpose. Left unset, the SDK falls back to
        # cloud.langfuse.com, and every traced prompt carries verbatim text
        # from real case documents - the same content the company gateway
        # exists to keep off third-party services. A half-configured install
        # must not quietly become an export of client material.
        logger.error(
            "%s and %s are set but %s is not. Refusing to trace: the SDK would "
            "default to Langfuse Cloud and send case-document text to a third "
            "party. Point %s at your own instance.",
            PUBLIC_KEY,
            SECRET_KEY,
            BASE_URL,
            BASE_URL,
        )
        return NullTracer()

    try:
        # Imported here rather than at module scope so an unconfigured process
        # never loads the SDK at all - it pulls in OpenTelemetry and its
        # exporters, none of which a machine that isn't tracing should pay for.
        from langfuse import Langfuse

        from observability.langfuse_tracer import LangfuseTracer

        return LangfuseTracer(
            Langfuse(public_key=public_key, secret_key=secret_key, base_url=base_url)
        )
    except Exception:
        # Configured but unbuildable - a bad URL, an SDK version mismatch. Same
        # rule as everywhere else in this package: log it, run untraced.
        logger.warning("Langfuse is configured but unusable - tracing disabled", exc_info=True)
        return NullTracer()
