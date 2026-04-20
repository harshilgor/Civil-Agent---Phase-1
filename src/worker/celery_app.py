"""Celery application for Civil Agent's async CV pipeline (Step 5 scaffold).

This is the **infrastructure skeleton** for Channels B (CAD) and C (image).
In Step 5 the tasks themselves are stubs that return a fixed synthetic
Building Graph; the real CV pipeline (SAM, CubiCasa, YOLO, OCR, …) is
wired in later steps via :mod:`backend.weights.loader`.

Design choices
--------------
* **Redis-only** broker + result backend.  No RabbitMQ, no SQS.
* **One GPU task per worker**.  ``worker_prefetch_multiplier = 1`` ensures
  a task never blocks on GPU contention with its neighbour on the same
  worker process.
* **Late acknowledgement**.  ``task_acks_late = True`` +
  ``task_reject_on_worker_lost = True`` means a crashed worker requeues
  its in-flight task rather than silently losing it.
* **STARTED state reported**.  ``task_track_started = True`` so the
  polling endpoint can differentiate *queued* from *processing* without
  any custom heartbeat.
* **Hard time limits**.  5-minute hard / 4-minute soft limits keep a
  runaway task from wedging the pool.

Everything that touches a model checkpoint is deferred until the
``worker_init`` signal fires in later steps — Step 5 intentionally keeps
that signal a no-op so the worker starts cleanly on a box without weights.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

try:
    from celery import Celery
    from celery.signals import task_failure, task_postrun, task_prerun

    _HAS_CELERY = True
except ImportError:  # pragma: no cover — worker extra not installed
    Celery = object  # type: ignore[assignment,misc]
    _HAS_CELERY = False

from src.config import settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Celery factory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Eager-mode safety gate
#
# ``task_always_eager`` makes every ``.delay()`` call execute synchronously
# in the calling process.  That is exactly what we want in tests (no
# broker required, deterministic behaviour) and exactly what we do NOT
# want in production: a deployment running the API process with eager
# mode on would silently execute all worker tasks inline, defeating the
# whole async architecture and holding the event loop on every CV run.
#
# To make this auditable we require an explicit opt-in via the
# ``CELERY_TASK_ALWAYS_EAGER`` environment variable.  Tests set it in
# :mod:`tests.conftest`; no deployment image should ever set it.  The
# flag is deliberately a separate env var (not a field on :class:`Settings`)
# so ``.env`` files cannot accidentally turn it on.
# ---------------------------------------------------------------------------

_EAGER_ENV_VAR = "CELERY_TASK_ALWAYS_EAGER"


def _eager_mode_requested() -> bool:
    return os.environ.get(_EAGER_ENV_VAR, "").strip().lower() in {"1", "true", "yes"}


_DEFAULT_CONF: dict[str, Any] = {
    # Broker / backend resilience.
    "broker_connection_retry_on_startup": True,
    "result_expires": 60 * 60 * 24,  # 24h
    # GPU-critical behaviour.
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
    "task_track_started": True,
    "task_reject_on_worker_lost": True,
    "task_time_limit": 300,
    "task_soft_time_limit": 240,
    # Serialization.
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,
}


def make_celery(*, eager: bool | None = None) -> "Celery":
    """Build the Celery application.

    Parameters
    ----------
    eager:
        Tri-state: ``None`` (default) consults the
        ``CELERY_TASK_ALWAYS_EAGER`` environment variable and only turns
        eager mode on when it is ``1`` / ``true`` / ``yes``.  Passing
        an explicit ``True`` / ``False`` overrides the env var — used by
        unit tests that need to rebuild an eager app independently of
        the session-wide configuration.

    Notes
    -----
    Eager mode must never be on in production.  The API process would
    otherwise execute every enqueued worker task inline, blocking the
    request handler for the full pipeline duration.  The env-var gate
    makes accidental enablement a one-line PR diff instead of a silent
    ``.env`` regression.
    """

    if not _HAS_CELERY:
        raise RuntimeError(
            "Celery is not installed. Install the 'worker' extra: "
            "pip install civil-agent[worker]"
        )

    app = Celery(
        "civil_agent",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["src.worker.tasks"],
    )
    app.conf.update(_DEFAULT_CONF)

    use_eager = _eager_mode_requested() if eager is None else bool(eager)
    if use_eager:
        logger.warning(
            "celery_eager_mode_enabled",
            reason=(
                "CELERY_TASK_ALWAYS_EAGER is set"
                if eager is None
                else "explicit caller override"
            ),
        )
        app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
        )
    return app


celery_app = make_celery() if _HAS_CELERY else None


# ---------------------------------------------------------------------------
# Structured per-task logging
# ---------------------------------------------------------------------------


if _HAS_CELERY:

    @task_prerun.connect
    def _task_prerun(task_id: str, task, *, args: Any = None, **_: Any) -> None:  # type: ignore[no-untyped-def]
        logger.info("task_prerun", task_id=task_id, task_name=task.name)

    @task_postrun.connect
    def _task_postrun(
        task_id: str, task, *, state: str = "SUCCESS", **_: Any
    ) -> None:  # type: ignore[no-untyped-def]
        logger.info(
            "task_postrun",
            task_id=task_id,
            task_name=task.name,
            state=state,
        )

    @task_failure.connect
    def _task_failure(task_id: str, exception, *, traceback=None, **_: Any) -> None:  # type: ignore[no-untyped-def]
        logger.error("task_failure", task_id=task_id, error=str(exception))


__all__ = ["celery_app", "make_celery"]
