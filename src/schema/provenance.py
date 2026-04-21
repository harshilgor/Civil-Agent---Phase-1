"""Provenance tracking — every Building Graph element can carry a record of
which detector / pipeline stage produced it.

The Phase 1 perception pipeline is a fan-in of multiple producers (CubiCasa
hourglass, SMP U-Net, YOLO-Seg wall fallback, symbol detector, VLM gap-fill,
direct CAD/IFC parsing, structured form, manual review).  When a downstream
stage — or a human reviewer — looks at a wall segment or room polygon they
must be able to trace it back to the producer that emitted it, the model
weights manifest hash that produced it, and the raw confidence score the
model itself reported (before any pipeline-level rescoring).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .enums import DetectorSource


class ProvenanceRecord(BaseModel):
    """Audit trail for a single Building Graph element.

    Attributes:
        detector_source: Which producer emitted the element.
        model_id: Stable identifier of the model variant
            (e.g. ``"cubicasa_hg_v1"``, ``"smp_unet_resnet34_cc5k_v0_2"``).
            ``None`` for non-ML producers (structured form, CAD, user override).
        model_version: Semantic version pulled from the weights manifest.
        weights_manifest_hash: SHA-256 of the manifest entry that resolved
            the weights file — guarantees reproducibility.
        run_id: Identifier of the pipeline run that produced this element
            (links back to the Celery job id on the API side).
        confidence_from_model: Raw model-reported confidence ``[0.0, 1.0]``,
            before any pipeline rescoring or completeness adjustment.
        notes: Free-form audit note (e.g. ``"merged with adjacent segment"``).
        created_at: UTC timestamp when the element was emitted.
    """

    detector_source: DetectorSource
    model_id: Optional[str] = Field(default=None, max_length=128)
    model_version: Optional[str] = Field(default=None, max_length=64)
    weights_manifest_hash: Optional[str] = Field(default=None, max_length=128)
    run_id: Optional[str] = Field(default=None, max_length=128)
    confidence_from_model: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
    )
