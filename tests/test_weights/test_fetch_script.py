"""Integration tests for ``scripts/fetch_weights.py``.

Exercises the CLI through two entry points:

  1. The importable :func:`main` — fast, keeps process startup cheap, and
     lets us share the tmp fixtures with the other ``test_weights/`` tests.
  2. A subprocess invocation — guards against import-time / shebang /
     sys.path regressions that ``main()`` would not catch.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "fetch_weights.py"


def _load_fetch_module():
    """Import ``scripts/fetch_weights.py`` as a module (no shell)."""

    spec = importlib.util.spec_from_file_location("_fetch_weights_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None  # for mypy / defensive
    spec.loader.exec_module(module)
    return module


class TestFetchWeightsVerifyOnly:
    def test_exit_zero_when_all_enabled_present(
        self,
        tmp_path: Path,
        tmp_manifest_path: Path,
        tmp_weights_artifact,
        capsys: pytest.CaptureFixture[str],
    ):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        module = _load_fetch_module()
        exit_code = module.main([
            "--verify-only",
            "--backend", "local",
            "--manifest", str(tmp_manifest_path),
            "--weights-dir", str(weights_dir),
        ])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "[ OK ]" in captured.out
        assert "wall_segmenter_residential" in captured.out
        # Disabled entries should not be promoted into failures.
        assert "[FAIL]" not in captured.out

    def test_exit_one_when_enabled_missing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        # Use an S3-only manifest so the local backend's vendor-path fallback
        # can't accidentally satisfy the lookup.
        manifest = tmp_path / "s3_only.yaml"
        manifest.write_text(
            """
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: cubicasa_hg_v1.pkl
    source:
      s3_key: models/cubicasa/cubicasa_hg_v1.pkl
""".lstrip(),
            encoding="utf-8",
        )
        empty = tmp_path / "empty-cache"
        empty.mkdir()

        module = _load_fetch_module()
        exit_code = module.main([
            "--verify-only",
            "--backend", "local",
            "--manifest", str(manifest),
            "--weights-dir", str(empty),
        ])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "[MISS]" in captured.out
        assert "wall_segmenter_residential" in captured.out


class TestFetchWeightsSlotSelection:
    def test_single_model_flag(
        self,
        tmp_path: Path,
        tmp_manifest_path: Path,
        tmp_weights_artifact,
        capsys: pytest.CaptureFixture[str],
    ):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        module = _load_fetch_module()
        exit_code = module.main([
            "--verify-only",
            "--backend", "local",
            "--manifest", str(tmp_manifest_path),
            "--weights-dir", str(weights_dir),
            "--model", "wall_segmenter_residential",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "wall_segmenter_residential" in out
        assert "yolo_wall_seg" not in out
        assert "wall_segmenter_commercial" not in out

    def test_unknown_model_rejected(
        self,
        tmp_path: Path,
        tmp_manifest_path: Path,
        tmp_weights_artifact,
        capsys: pytest.CaptureFixture[str],
    ):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        module = _load_fetch_module()
        exit_code = module.main([
            "--verify-only",
            "--backend", "local",
            "--manifest", str(tmp_manifest_path),
            "--weights-dir", str(weights_dir),
            "--model", "nope",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "unknown slot" in err

    def test_all_flag_includes_disabled(
        self,
        tmp_path: Path,
        tmp_manifest_path: Path,
        tmp_weights_artifact,
        capsys: pytest.CaptureFixture[str],
    ):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        module = _load_fetch_module()
        exit_code = module.main([
            "--verify-only",
            "--backend", "local",
            "--manifest", str(tmp_manifest_path),
            "--weights-dir", str(weights_dir),
            "--all",
        ])
        # All enabled entries present → exit 0; disabled entries are SKIP not FAIL.
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "[SKIP]" in out
        assert "yolo_wall_seg" in out


class TestFetchWeightsSubprocess:
    def test_invoked_as_script(
        self,
        tmp_path: Path,
        tmp_manifest_path: Path,
        tmp_weights_artifact,
    ):
        artefact, _sha, _size = tmp_weights_artifact
        weights_dir = tmp_path / "weights-cache"
        weights_dir.mkdir()
        shutil.copy(artefact, weights_dir / artefact.name)

        proc = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT),
                "--verify-only",
                "--backend", "local",
                "--manifest", str(tmp_manifest_path),
                "--weights-dir", str(weights_dir),
            ],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "[ OK ]" in proc.stdout
        assert "wall_segmenter_residential" in proc.stdout

    def test_help_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=30,
        )
        assert proc.returncode == 0
        assert "fetch_weights" in proc.stdout
