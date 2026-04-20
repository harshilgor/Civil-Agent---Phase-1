"""Celery application factory tests (Step 5)."""

from __future__ import annotations

import pytest

celery = pytest.importorskip("celery")


def test_celery_app_is_installed() -> None:
    from src.worker.celery_app import celery_app

    assert celery_app is not None
    assert celery_app.main == "civil_agent"


def test_gpu_critical_conf_is_set() -> None:
    """The GPU-mode knobs specified in the module docstring must be live.

    These are the settings that prevent two tasks from fighting over the
    same GPU inside one worker process (``prefetch=1``), keep late acks
    / reject-on-loss for crash safety, and surface ``STARTED`` so the
    frontend progress bar can move before the graph is ready.
    """

    from src.worker.celery_app import celery_app

    conf = celery_app.conf
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_acks_late is True
    assert conf.task_track_started is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.task_time_limit == 300
    assert conf.task_soft_time_limit == 240
    assert conf.result_expires == 60 * 60 * 24


def test_serializer_is_json_only() -> None:
    """JSON-only serialization — no pickle, no custom deserialisers."""

    from src.worker.celery_app import celery_app

    conf = celery_app.conf
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.timezone == "UTC"


def test_broker_and_backend_wired_from_settings() -> None:
    from src.config import settings
    from src.worker.celery_app import celery_app

    assert celery_app.conf.broker_url == settings.celery_broker_url
    assert celery_app.conf.result_backend == settings.celery_result_backend


def test_tasks_are_registered() -> None:
    """The two Step-5 stub tasks must be visible in ``celery_app.tasks``."""

    from src.worker.celery_app import celery_app
    # Trigger task module load.
    import src.worker.tasks  # noqa: F401

    assert "civil_agent.process_floor_plan" in celery_app.tasks
    assert "civil_agent.process_cad_file" in celery_app.tasks


def test_eager_factory_toggles_always_eager() -> None:
    """``make_celery(eager=True)`` should enable ``task_always_eager``."""

    from src.worker.celery_app import make_celery

    eager_app = make_celery(eager=True)
    assert eager_app.conf.task_always_eager is True
    assert eager_app.conf.task_eager_propagates is True
    # Sanity: the non-eager defaults are unchanged on the fresh app.
    assert eager_app.conf.worker_prefetch_multiplier == 1
