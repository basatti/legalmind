"""Settings that depend on *where* the app runs.

The bar for adding something here is deliberately narrow: a value that changes
with the deployment, not with the domain. Session TTL is the clarifying
counter-example — it lives in `services/auth_service.py` and stays there,
because "a login lasts 24 hours" is a rule about the product and is identical
on every machine. Putting it here would imply it is a knob someone is expected
to turn per environment.

Before this module existed, environment-driven values were read ad hoc wherever
they were needed (`RAG_MULTI_STEP_ENABLED` in `graph/builder.py`, `STORAGE_DIR`
in `foundation/storage.py`), each with its own private parsing convention. Those
two are left alone — moving them is not worth the churn — but new ones belong
here.

Read once at import. Changing the environment means restarting the process,
which is the honest behaviour: a setting that can change under a running
request is a setting two requests can disagree about.
"""

import os

DEVELOPMENT = "development"
PRODUCTION = "production"

KNOWN_ENVIRONMENTS = frozenset({DEVELOPMENT, PRODUCTION})

DEFAULT_ENVIRONMENT = DEVELOPMENT
"""What an unset ENVIRONMENT means.

Defaulting to development is defaulting to the *less* protected behaviour, which
is the opposite of how `RAG_MULTI_STEP_ENABLED` treats an unset variable, and it
is a deliberate exception rather than an oversight.

LegalMind is a local-only training project. Nothing is deployed, nothing is
served over a network the team does not own, and the only thing the safe default
would buy is protection against forgetting a variable during a deployment that
does not happen. What it would cost is real: a `Secure` cookie is not stored by
a browser over plain HTTP unless the origin is localhost, so demoing the app
from another machine over a LAN address or a Tailscale hostname would present as
"login succeeds, then every request is 401" — the least diagnosable failure this
project could choose to invent for itself.

**If LegalMind is ever deployed anywhere, this default must flip to PRODUCTION**,
and that is the entire change: one constant here, plus keeping
`ENVIRONMENT=development` in `.env.example` and `docker-compose.yml` so local
work is unaffected.
"""


def resolve_environment(raw: str) -> str:
    """Normalise a raw ENVIRONMENT value, rejecting anything unrecognised.

    Absence and a typo are treated differently on purpose. An unset variable is
    a decision this project has made and written down above, so it resolves
    quietly to the default. A *misspelled* variable is not a decision — nobody
    typed "developement" meaning anything — so it raises here rather than
    silently resolving to the opposite of what its author intended.

    Same shape as the `DATABASE_URL` guard in `tests/conftest.py`: refuse loudly
    at import, with the offending value in the message, instead of proceeding on
    a guess. The cost of guessing wrong is a confusing runtime failure much
    further from its cause.
    """
    value = raw.strip().lower()

    if not value:
        return DEFAULT_ENVIRONMENT

    if value not in KNOWN_ENVIRONMENTS:
        allowed = ", ".join(sorted(KNOWN_ENVIRONMENTS))
        raise RuntimeError(
            f"ENVIRONMENT is set to {raw!r}, which is not a known environment. "
            f"Use one of: {allowed} — or leave it unset for {DEFAULT_ENVIRONMENT}."
        )

    return value


DEFAULT_SESSION_REAP_INTERVAL_MINUTES = 60
"""How often the ingestion worker sweeps expired sessions away.

An hour is chosen to be uninteresting. Sessions are already unusable the moment
they expire — `AuthService` rejects them on sight — so this only controls how
long dead rows linger, and nothing observable depends on the number. Sweeping
every cycle instead would mean a query every five seconds to delete nothing.
"""


def resolve_reap_interval_minutes(raw: str) -> int:
    """Parse SESSION_REAP_INTERVAL_MINUTES, refusing anything unusable.

    Same treatment as `resolve_environment`: unset is fine and means the
    default, but a value that cannot be honoured stops the process rather than
    being quietly replaced. A misread interval is invisible — the worker keeps
    draining the queue and simply never reaps, which is the failure this whole
    item exists to fix.
    """
    value = raw.strip()

    if not value:
        return DEFAULT_SESSION_REAP_INTERVAL_MINUTES

    try:
        minutes = int(value)
    except ValueError:
        raise RuntimeError(
            f"SESSION_REAP_INTERVAL_MINUTES is set to {raw!r}, which is not a whole "
            f"number of minutes. Leave it unset for {DEFAULT_SESSION_REAP_INTERVAL_MINUTES}."
        ) from None

    if minutes <= 0:
        raise RuntimeError(
            f"SESSION_REAP_INTERVAL_MINUTES must be greater than zero, not {minutes}. "
            "There is no 'off' value — stop the worker if the sweep is not wanted."
        )

    return minutes


ENVIRONMENT = resolve_environment(os.environ.get("ENVIRONMENT", ""))

COOKIE_SECURE = ENVIRONMENT != DEVELOPMENT
"""Whether the session cookie carries the `Secure` attribute.

Expressed as "not development" rather than "is production" so that adding a
third environment later — staging, a demo box — protects it by default and has
to opt *out* deliberately. Only local development has a reason to go without.

Currently False in every environment anyone runs, which is the point of writing
it down: `secure=False` hardcoded in the router was an unexamined constant with
a comment describing an intention no code implemented. This is the same value,
reached by a rule, in a place that explains itself.
"""

SESSION_REAP_INTERVAL_MINUTES = resolve_reap_interval_minutes(
    os.environ.get("SESSION_REAP_INTERVAL_MINUTES", "")
)
