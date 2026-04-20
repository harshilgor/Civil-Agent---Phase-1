"""Helpers for stamping Building Graph elements with auditable provenance.

Every element produced by a Phase 1 channel (structured form, CAD parse, CV
pipeline output) must carry a :class:`~src.schema.provenance.ProvenanceRecord`
so downstream stages and reviewers can trace who emitted it.  These helpers
build the ``ProvenanceRecord`` instances with the right ``detector_source`` and
``run_id`` pre-wired.
"""

from __future__ import annotations

from typing import Optional

from src.schema.enums import DetectorSource
from src.schema.provenance import ProvenanceRecord


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


__all__ = ["structured_form_provenance", "user_override_provenance"]
