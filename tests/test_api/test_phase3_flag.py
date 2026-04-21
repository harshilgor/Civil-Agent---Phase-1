"""Tests that the ``PHASE3_ENABLED`` feature flag correctly gates the
mounting of the Phase 3 router on the FastAPI application.

Phase 3 routes ship under the ``/api/v1/phase3`` prefix.  When the flag is
``False`` (default), no Phase 3 routes should be present and the Phase 3
module should not be imported at app-construction time.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _reload_app(monkeypatch: pytest.MonkeyPatch, *, phase3_enabled: bool):
    """Reload the API stack with the requested flag value.

    The settings singleton is created at import time, so we have to evict
    the relevant modules from ``sys.modules`` before re-importing.
    """

    monkeypatch.setenv("PHASE3_ENABLED", "true" if phase3_enabled else "false")
    for mod in [
        "src.main",
        "src.api.router",
        "src.config",
    ]:
        sys.modules.pop(mod, None)

    config_module = importlib.import_module("src.config")
    main_module = importlib.import_module("src.main")
    return config_module.settings, main_module.app


def _route_paths(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


class TestPhase3FeatureFlag:
    def test_flag_defaults_to_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PHASE3_ENABLED", raising=False)
        for mod in ["src.config"]:
            sys.modules.pop(mod, None)
        config_module = importlib.import_module("src.config")
        assert config_module.settings.phase3_enabled is False

    def test_disabled_does_not_mount_phase3_routes(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Make sure the Phase 3 module is not preloaded from a prior test.
        for mod in [m for m in list(sys.modules) if m.startswith("src.phase3")]:
            sys.modules.pop(mod, None)

        settings, app = _reload_app(monkeypatch, phase3_enabled=False)
        assert settings.phase3_enabled is False
        paths = _route_paths(app)
        assert not any(p.startswith("/api/v1/phase3") for p in paths), (
            f"Phase 3 routes should not be mounted when flag is off: "
            f"found {[p for p in paths if 'phase3' in p]}"
        )
        assert not any(m.startswith("src.phase3") for m in sys.modules), (
            "src.phase3 should not be imported when the flag is off"
        )

    def test_enabled_mounts_phase3_routes(self, monkeypatch: pytest.MonkeyPatch):
        settings, app = _reload_app(monkeypatch, phase3_enabled=True)
        assert settings.phase3_enabled is True
        paths = _route_paths(app)
        phase3_paths = [p for p in paths if p.startswith("/api/v1/phase3")]
        assert phase3_paths, (
            f"Expected at least one /api/v1/phase3 route when flag is on; "
            f"got {sorted(paths)}"
        )

    def teardown_method(self):
        # Reset module state so other test modules see a clean app.
        for mod in [
            "src.main",
            "src.api.router",
            "src.config",
        ]:
            sys.modules.pop(mod, None)
