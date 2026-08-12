"""One pass of the ingestion worker's loop.

`run_forever` never returns, so everything it decided was untestable and sat at
53% once `--cov=worker_main` started measuring it. `run_one_cycle` holds those
decisions now; what is left in the loop is the `while`, the sleep and the
session lifetime, none of which a unit test can say anything useful about.

The worker here is a stand-in rather than the real `IngestionWorker`: this is
testing the *order and conditions* of a cycle, not ingestion, which
`test_ingestion_worker.py` already covers against a real queue.
"""

import logging
from datetime import UTC, datetime, timedelta

from worker_main import SESSION_REAP_INTERVAL, run_one_cycle


class FakeWorker:
    """Records what the cycle asked it to do."""

    def __init__(self, did_work: bool = False, reclaimed: int = 0):
        self._did_work = did_work
        self._reclaimed = reclaimed
        self.calls: list[str] = []

    def reclaim_stale(self) -> int:
        self.calls.append("reclaim_stale")
        return self._reclaimed

    def run_once(self) -> bool:
        self.calls.append("run_once")
        return self._did_work


def test_a_cycle_reclaims_before_it_claims(session):
    """Order matters: a job left RUNNING by a dead worker is only recoverable
    before something else claims the next PENDING one."""
    worker = FakeWorker()

    run_one_cycle(session, worker, datetime.now(UTC), None)  # type: ignore[arg-type]

    assert worker.calls == ["reclaim_stale", "run_once"]


def test_the_cycle_reports_whether_it_did_work(session):
    """`run_forever` sleeps only when nothing was found, so this boolean is the
    difference between draining a queue promptly and idling through it."""
    now = datetime.now(UTC)

    did_work, _ = run_one_cycle(session, FakeWorker(did_work=True), now, None)  # type: ignore[arg-type]
    assert did_work is True

    did_work, _ = run_one_cycle(session, FakeWorker(did_work=False), now, None)  # type: ignore[arg-type]
    assert did_work is False


def test_a_first_cycle_reaps_and_stamps_the_clock(session):
    now = datetime.now(UTC)

    _, last_reap = run_one_cycle(session, FakeWorker(), now, None)  # type: ignore[arg-type]

    assert last_reap == now


def test_a_cycle_inside_the_interval_does_not_reap(session):
    """The reason the interval exists: without it the sweep would run every
    five seconds to delete nothing."""
    now = datetime.now(UTC)
    recent = now - (SESSION_REAP_INTERVAL / 2)

    _, last_reap = run_one_cycle(session, FakeWorker(), now, recent)  # type: ignore[arg-type]

    assert last_reap == recent


def test_a_cycle_past_the_interval_reaps_again(session):
    now = datetime.now(UTC)
    stale = now - SESSION_REAP_INTERVAL - timedelta(seconds=1)

    _, last_reap = run_one_cycle(session, FakeWorker(), now, stale)  # type: ignore[arg-type]

    assert last_reap == now


def test_reclaimed_jobs_are_reported(session, caplog):
    """A dead worker's abandoned job is worth a line in the log — silently
    recovering it hides that a worker died."""
    caplog.set_level(logging.WARNING)

    run_one_cycle(session, FakeWorker(reclaimed=3), datetime.now(UTC), None)  # type: ignore[arg-type]

    assert "reclaimed 3 job(s)" in caplog.text


def test_nothing_reclaimed_stays_quiet(session, caplog):
    caplog.set_level(logging.WARNING)

    run_one_cycle(session, FakeWorker(reclaimed=0), datetime.now(UTC), None)  # type: ignore[arg-type]

    assert "reclaimed" not in caplog.text


def test_a_failing_reap_does_not_stop_the_queue(session, caplog):
    """The whole reason the sweep swallows its errors: ingestion is this
    process's actual job, and it must still run.
    """

    class BrokenSession:
        def exec(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("connection is gone")

    worker = FakeWorker(did_work=True)

    did_work, _ = run_one_cycle(BrokenSession(), worker, datetime.now(UTC), None)  # type: ignore[arg-type]

    assert did_work is True
    assert "run_once" in worker.calls
    assert "expired-session sweep failed" in caplog.text
