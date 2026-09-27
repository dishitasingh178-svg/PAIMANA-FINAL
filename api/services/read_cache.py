"""Correctness-first cache for expensive whole-portfolio reads.

The early-warning triage scores every alert against portfolio-wide values
(95th-percentile exposure, latest reporting month), which costs seconds of
Python per request but only changes when the underlying rows change. A cached
value is reused only while ALL of these hold:

1. No in-process ORM write touched Alert, Prediction, Project or ProjectUpdate
   since it was computed (flush / commit / rollback / bulk update hooks below),
   which covers ingestion, prediction runs, the alert engine and status changes,
   including in-place edits that leave no timestamp.
2. The database fingerprint (row counts, max ids, change timestamps) is
   unchanged, which catches writes made by other processes (maintenance
   scripts, additional workers). It is recorded at the first reuse rather
   than at compute time, so a cold computation costs no extra query (the
   triage query budget is tested); a write by another process in the gap
   before that first reuse is covered by the age limit below.
3. It is younger than MAX_AGE_SECONDS, which bounds anything neither check
   can see (for example a manual in-place SQL edit of a project row).

Callers must treat cached values as read-only.
"""

import threading
import time
import uuid

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from api.models.models import Alert, Prediction, Project, ProjectUpdate


MAX_AGE_SECONDS = 120

_WATCHED = (Alert, Prediction, Project, ProjectUpdate)

_FINGERPRINT_SQL = text(
    """
    SELECT
        (SELECT count(*) FROM projects),
        (SELECT max(id) FROM project_updates),
        (SELECT count(*) FROM predictions),
        (SELECT max(prediction_id) FROM predictions),
        (SELECT max(generated_at) FROM predictions),
        (SELECT count(*) FROM alerts),
        (SELECT max(alert_id) FROM alerts),
        (SELECT max(triggered_at) FROM alerts),
        (SELECT max(status_updated_at) FROM alerts),
        (SELECT max(evidence_updated_at) FROM alerts)
    """
)

_state_lock = threading.Lock()
_compute_lock = threading.RLock()   # re-entrant: one cached value may build on another
_generation = 0
_entries = {}                       # name -> [generation, bind_token, fingerprint | None, created_at, value]


def invalidate() -> None:
    global _generation
    with _state_lock:
        _generation += 1
        _entries.clear()


def _bind_token(db: Session) -> str:
    """Stable identity of the database behind this session (never reused)."""
    bind = db.get_bind()
    token = getattr(bind, "_pm_read_cache_token", None)
    if token is None:
        token = f"{uuid.uuid4().hex}:{bind.url}"
        bind._pm_read_cache_token = token
    return token


def _reusable(entry, db: Session, token: str) -> bool:
    if (
        entry is None
        or entry[0] != _generation
        or entry[1] != token
        or time.monotonic() - entry[3] >= MAX_AGE_SECONDS
    ):
        return False
    fingerprint = tuple(db.execute(_FINGERPRINT_SQL).one())
    with _state_lock:
        if entry[2] is None and entry[0] == _generation:
            entry[2] = fingerprint
    return entry[2] == fingerprint


def cached(name: str, db: Session, compute):
    token = _bind_token(db)
    entry = _entries.get(name)
    if _reusable(entry, db, token):
        return entry[4]

    # One computation at a time: concurrent misses wait and reuse the result
    # instead of each spending seconds (and a pooled DB connection) on it.
    with _compute_lock:
        entry = _entries.get(name)
        if entry is not None and entry[2] is not None and _reusable(entry, db, token):
            return entry[4]
        generation = _generation
        started = time.perf_counter()
        value = compute()
        print(f"[PERF] {name}: computed in {(time.perf_counter() - started) * 1000:.0f} ms", flush=True)
        with _state_lock:
            # A write that happened while computing makes this result unsafe to keep.
            if generation == _generation:
                _entries[name] = [generation, token, None, time.monotonic(), value]
        return value


# ---------------------------------------------------------------------------
# In-process invalidation
# ---------------------------------------------------------------------------

def _touches_watched(session: Session) -> bool:
    return any(isinstance(obj, _WATCHED) for obj in (*session.new, *session.dirty, *session.deleted))


@event.listens_for(Session, "after_flush")
def _after_flush(session, _flush_context):
    if _touches_watched(session):
        session.info["pm_read_cache_dirty"] = True
        invalidate()


@event.listens_for(Session, "after_commit")
def _after_commit(session):
    # Readers may have cached pre-commit data between the flush and the commit.
    if session.info.pop("pm_read_cache_dirty", False):
        invalidate()


@event.listens_for(Session, "after_rollback")
def _after_rollback(session):
    # A value computed inside the rolled-back transaction must not survive it.
    if session.info.pop("pm_read_cache_dirty", False):
        invalidate()


@event.listens_for(Session, "do_orm_execute")
def _after_bulk_write(orm_execute_state):
    if orm_execute_state.is_update or orm_execute_state.is_delete or orm_execute_state.is_insert:
        orm_execute_state.session.info["pm_read_cache_dirty"] = True
        invalidate()
