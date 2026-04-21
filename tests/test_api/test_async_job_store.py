"""Unit tests for :mod:`src.api.async_job_store`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api import async_job_store
from src.schema.building_graph import BuildingGraph


def _synthetic_graph() -> BuildingGraph:
    from src.worker.tasks import run_floor_plan_stub

    payload = run_floor_plan_stub("job-fixture")
    return BuildingGraph.model_validate(payload["building_graph"])


class TestStateMachine:
    def test_register_creates_queued_record(self) -> None:
        record = async_job_store.register("j1", channel="image", filename="f.png")
        assert record.status == "queued"
        assert record.channel == "image"
        assert record.building_graph is None
        assert async_job_store.get("j1") is record

    def test_attach_celery_task_flips_to_processing(self) -> None:
        async_job_store.register("j2", channel="cad")
        record = async_job_store.attach_celery_task("j2", "celery-task-42")
        assert record is not None
        assert record.status == "processing"
        assert record.celery_task_id == "celery-task-42"
        assert record.progress_percent >= 1.0

    def test_mark_completed_stores_graph(self) -> None:
        async_job_store.register("j3", channel="image")
        graph = _synthetic_graph()
        record = async_job_store.mark_completed("j3", graph)
        assert record is not None
        assert record.status == "completed"
        assert record.progress_percent == 100.0
        assert record.building_graph is graph

    def test_mark_failed_records_error(self) -> None:
        async_job_store.register("j4", channel="cad")
        record = async_job_store.mark_failed("j4", "kaboom")
        assert record is not None
        assert record.status == "failed"
        assert record.error == "kaboom"

    def test_unknown_ids_return_none(self) -> None:
        assert async_job_store.get("ghost") is None
        assert async_job_store.mark_completed("ghost", _synthetic_graph()) is None
        assert async_job_store.mark_failed("ghost", "x") is None
        assert async_job_store.attach_celery_task("ghost", "tid") is None


class TestReconcileFromAsyncResult:
    def _fake_result(self, *, ready=True, success=True, payload=None, err=None) -> MagicMock:
        ar = MagicMock()
        ar.ready.return_value = ready
        ar.successful.return_value = success
        ar.result = payload if success else err
        return ar

    def test_success_marks_completed_with_graph(self) -> None:
        async_job_store.register("jr1", channel="image")
        graph = _synthetic_graph()
        payload = {"building_graph": graph.model_dump(mode="json")}
        ar = self._fake_result(payload=payload)

        record = async_job_store.reconcile_from_async_result("jr1", ar)
        assert record is not None
        assert record.status == "completed"
        assert record.building_graph is not None
        assert record.building_graph.metadata.job_id == graph.metadata.job_id

    def test_failure_marks_failed(self) -> None:
        async_job_store.register("jr2", channel="cad")
        ar = self._fake_result(success=False, err=RuntimeError("broke"))

        record = async_job_store.reconcile_from_async_result("jr2", ar)
        assert record is not None
        assert record.status == "failed"
        assert "broke" in record.error

    def test_not_ready_leaves_state_alone(self) -> None:
        async_job_store.register("jr3", channel="image")
        async_job_store.attach_celery_task("jr3", "tid")
        ar = self._fake_result(ready=False)

        record = async_job_store.reconcile_from_async_result("jr3", ar)
        assert record is not None
        assert record.status == "processing"
        assert record.building_graph is None

    def test_terminal_records_are_not_clobbered(self) -> None:
        async_job_store.register("jr4", channel="image")
        async_job_store.mark_failed("jr4", "first-fail")
        ar = self._fake_result(payload={"building_graph": _synthetic_graph().model_dump(mode="json")})

        record = async_job_store.reconcile_from_async_result("jr4", ar)
        assert record is not None
        assert record.status == "failed"
        assert record.error == "first-fail"

    def test_success_without_graph_payload_marks_failed(self) -> None:
        async_job_store.register("jr5", channel="image")
        ar = self._fake_result(payload={"status": "ok"})  # missing building_graph

        record = async_job_store.reconcile_from_async_result("jr5", ar)
        assert record is not None
        assert record.status == "failed"
        assert "building_graph" in record.error

    def test_unknown_id_is_noop(self) -> None:
        ar = self._fake_result(payload={"building_graph": _synthetic_graph().model_dump(mode="json")})
        assert async_job_store.reconcile_from_async_result("ghost", ar) is None


class TestRefreshIntegration:
    def test_refresh_with_no_celery_task_is_noop(self) -> None:
        async_job_store.register("jf1", channel="image")
        record = async_job_store.refresh("jf1")
        assert record is not None
        assert record.status == "queued"

    def test_refresh_unknown_id_returns_none(self) -> None:
        assert async_job_store.refresh("nope") is None

    def test_refresh_terminal_record_short_circuits(self) -> None:
        """Completed records don't re-fetch from the broker."""

        async_job_store.register("jf2", channel="cad")
        graph = _synthetic_graph()
        async_job_store.mark_completed("jf2", graph)
        record = async_job_store.refresh("jf2")
        assert record is not None
        assert record.status == "completed"
        assert record.building_graph is graph


def test_reset_for_tests_clears_store() -> None:
    async_job_store.register("before", channel="image")
    async_job_store._reset_for_tests()
    assert async_job_store.get("before") is None
