"""Shared fixtures for the weights-manifest test suite."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


def _fixture_manifest_body(local_path: Path, sha256: str, size_bytes: int) -> str:
    """Return a valid manifest YAML body referencing the supplied artefact."""

    return f"""
schema_version: "1.0.0"
models:
  wall_segmenter_residential:
    enabled: true
    architecture: cubicasa_hg
    model_id: cubicasa_hg_v1
    model_version: "1.0.0"
    filename: {local_path.name}
    sha256: {sha256}
    size_bytes: {size_bytes}
    num_classes: 44
    params:
      bootstrap_n_classes: 51
      tta_rotations: 4
    source:
      local_path: {local_path.as_posix()}
      s3_key: models/wall_segmenter/cubicasa_hg_v1.pkl

  wall_segmenter_commercial:
    enabled: false
    architecture: smp_unet
    model_id: smp_unet_resnet34_cc5k
    model_version: "0.2.0"
    filename: smp_unet_resnet34_cc5k_v0_2.pth
    num_classes: 7
    params:
      encoder_name: resnet34
      classes: 7
    source:
      s3_key: models/wall_segmenter/smp_unet_resnet34_cc5k_v0_2.pth

  yolo_wall_seg:
    enabled: false
    architecture: yolov8_seg
    model_id: yolo_wall_seg
    model_version: "0.1.0"
    filename: yolo_wall_seg_v0_1.pt
    params:
      conf_threshold: 0.25
    source:
      s3_key: models/yolo_wall_seg/yolo_wall_seg_v0_1.pt
""".lstrip()


@pytest.fixture()
def tmp_weights_artifact(tmp_path: Path) -> tuple[Path, str, int]:
    """Create a small fake weights file and return (path, sha256, size)."""

    payload = b"fake-weights-bytes-" * 128  # 2304 bytes — deterministic
    path = tmp_path / "cubicasa_hg_v1.pkl"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest(), len(payload)


@pytest.fixture()
def tmp_manifest_path(tmp_path: Path, tmp_weights_artifact) -> Path:
    """Write a manifest YAML pointing at ``tmp_weights_artifact`` and return it."""

    artefact, sha, size = tmp_weights_artifact
    body = _fixture_manifest_body(artefact, sha, size)
    manifest = tmp_path / "weights_manifest.yaml"
    manifest.write_text(body, encoding="utf-8")
    return manifest
