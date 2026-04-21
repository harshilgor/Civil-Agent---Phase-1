"""Helpers for stamping Building Graph elements with auditable provenance.

Every element produced by a Phase 1 channel (structured form, CAD parse, CV
pipeline output) must carry a :class:`~src.schema.provenance.ProvenanceRecord`
so downstream stages and reviewers can trace who emitted it.  These helpers
build the ``ProvenanceRecord`` instances with the right ``detector_source`` and
``run_id`` pre-wired.
"""

from __future__ import annotations

from typing import Optional

from src.schema.enums import DetectorSource, InputSource
from src.schema.provenance import ProvenanceRecord


# ---------------------------------------------------------------------------
# Channel B: CAD-sourced elements
# ---------------------------------------------------------------------------

_CAD_DETECTOR_FOR_INPUT: dict[InputSource, DetectorSource] = {
    InputSource.DXF_FILE: DetectorSource.CAD_DIRECT,
    InputSource.DWG_FILE: DetectorSource.CAD_DIRECT,
    InputSource.IFC_FILE: DetectorSource.IFC_DIRECT,
}


def structured_form_provenance(
    *,
    run_id: str,
    notes: Optional[str] = None,
) -> ProvenanceRecord:
    """Provenance stamp for elements created from a structured-form payload.

    Channel A emits no ML inference — every element is a literal echo of the
    form fields or a deterministic derivation from them — so ``model_id``,
    ``model_version``, and ``weights_manifest_hash`` are intentionally
    ``None``.  ``confidence_from_model`` is set to ``1.0`` because the input
    is user-verified and there is no ambiguity in the producer.
    """

    return ProvenanceRecord(
        detector_source=DetectorSource.STRUCTURED_FORM,
        run_id=run_id,
        confidence_from_model=1.0,
        notes=notes,
    )


def user_override_provenance(
    *,
    run_id: str,
    notes: Optional[str] = None,
) -> ProvenanceRecord:
    """Provenance stamp for elements (or overrides) supplied by the human reviewer.

    Used by the ``POST /api/v1/jobs/{job_id}/review`` endpoint when the user
    accepts, modifies, or adds an element during the review step.
    """

    return ProvenanceRecord(
        detector_source=DetectorSource.USER_OVERRIDE,
        run_id=run_id,
        confidence_from_model=1.0,
        notes=notes,
    )


def cad_provenance(
    *,
    input_source: InputSource,
    run_id: str,
    notes: Optional[str] = None,
) -> ProvenanceRecord:
    """Provenance stamp for elements parsed directly from a CAD/IFC file.

    DXF and DWG (the latter after ODA conversion) map to
    ``DetectorSource.CAD_DIRECT``; IFC maps to
    ``DetectorSource.IFC_DIRECT`` so the review UI can differentiate an
    IFC submission (authoritative BIM geometry) from a DXF (typically a
    2D drawing with more inferred structure).

    Channel B runs no ML, so ``model_id`` / ``weights_manifest_hash`` stay
    ``None`` and ``confidence_from_model`` is set to ``1.0`` — every
    element is a literal echo of what the source file carried.
    """

    detector = _CAD_DETECTOR_FOR_INPUT.get(input_source)
    if detector is None:
        raise ValueError(
            f"cad_provenance() does not support input_source={input_source!r}; "
            f"expected one of {sorted(s.value for s in _CAD_DETECTOR_FOR_INPUT)}."
        )

    return ProvenanceRecord(
        detector_source=detector,
        run_id=run_id,
        confidence_from_model=1.0,
        notes=notes,
    )


def vlm_provenance(
    *,
    run_id: str,
    model_id: str,
    confidence: Optional[float] = None,
    notes: Optional[str] = None,
) -> ProvenanceRecord:
    """Provenance stamp for elements (or classifications) produced by a VLM.

    Channel C's Stage-2 building-type classifier is the first consumer:
    Claude vision emits a :class:`~src.schema.enums.BuildingType` plus a
    self-reported confidence, and every element whose classification
    depends on that call (today just ``metadata.inferred_building_type``,
    in Step 9 also room labels / wall disambiguations that couldn't be
    resolved by the deterministic detectors) carries a record with
    ``detector_source=DetectorSource.VLM_GAP_FILL``.

    ``model_id`` captures the exact Claude model string
    (e.g. ``"claude-sonnet-4-20250514"``) so the manifest-selection audit
    trail can tie a classification back to the inference that produced it.
    """

    return ProvenanceRecord(
        detector_source=DetectorSource.VLM_GAP_FILL,
        run_id=run_id,
        model_id=model_id,
        confidence_from_model=confidence,
        notes=notes,
    )


__all__ = [
    "cad_provenance",
    "structured_form_provenance",
    "user_override_provenance",
    "vlm_provenance",
]
