# Benchmark overview

- Generated: **2026-04-18T01:47:55.050449+00:00**
- Scope: Phase 1 (Building Graph) and Phase 2 (Structural Abstraction Engine) via `src/` pipelines.
- **Incomplete by design where assets are missing**: several required PDF/raster cross-input files are not present under `data/`. Those cases are recorded as unresolved rather than silently passing.

## Benchmark file inventory (repository)

### IFC files found under `data/`

- `data\NBU_MedicalClinic\NBU_MedicalClinic_Arch-Optimized.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Arch.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-CON-Optimized.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-CON.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-ELE.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-HVAC.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-MEP-Optimized.ifc`
- `data\NBU_MedicalClinic\NBU_MedicalClinic_Eng-MEP.ifc`
- `data\Office_A_20110811.ifc`
- `data\Office_A_20110811_optimized.ifc`
- `data\Office_MEP_20110811.ifc`
- `data\Office_MEP_20110811_optimized.ifc`
- `data\Office_S_20110811.ifc`
- `data\Office_S_20110811_optimized.ifc`

### Other formats

- **DXF**: not shipped in `data/`; benchmark generates a temporary DXF (same pattern as `tests/test_parsers/test_dxf_parser.py`).
- **PDF / production rasters**: no `*.pdf` or benchmark PNGs in `data/`; synthetic rasters are written to `reports/benchmark_cache/`.

## Summary counts

| Metric | Value |
| --- | --- |
| Total cases | 24 |
| Phase 1 success | 21 |
| Phase 2 success | 21 |

## Dataset / case inventory

| case_id | category | building_type | input_type | P1 | P2 |
| --- | --- | --- | --- | --- | --- |
| hp_office_struct | happy_path | office | structured_form | PASS | PASS |
| hp_duplex_struct | happy_path | residential_duplex | structured_form | PASS | PASS |
| hp_clinic_struct | happy_path | healthcare_clinic | structured_form | PASS | PASS |
| hp_barracks_struct | happy_path | small_office_barracks | structured_form | PASS | PASS |
| ifc_office_s | happy_path | office | IFC | PASS | PASS |
| ifc_office_a | happy_path | office | IFC | PASS | PASS |
| ifc_clinic_arch | happy_path | healthcare_clinic | IFC | PASS | PASS |
| dxf_synthetic_baseline | happy_path | office | DXF | PASS | PASS |
| raster_office_clean | cross_input | office | floor_plan_image | PASS | PASS |
| raster_office_blur | robustness | office | floor_plan_image | PASS | PASS |
| raster_office_skew | robustness | office | floor_plan_image | PASS | PASS |
| raster_office_crop | robustness | office | floor_plan_image | PASS | PASS |
| raster_compressed_scan | robustness | office | floor_plan_image | PASS | PASS |
| raster_low_resolution | robustness | office | floor_plan_image | PASS | PASS |
| raster_missing_dimension_labels | robustness | office | floor_plan_image | PASS | PASS |
| raster_ambiguous_unit_labels | robustness | office | floor_plan_image | PASS | PASS |
| raster_no_grid_labels | robustness | office | floor_plan_image | PASS | PASS |
| adv_open_lobby_struct | adversarial | office | structured_form | PASS | PASS |
| adv_atrium_struct | adversarial | retail_atrium | structured_form | PASS | PASS |
| adv_broken_stack_struct | adversarial | office | structured_form | PASS | PASS |
| adv_irregular_struct | adversarial | mixed_use | structured_form | PASS | PASS |
| cross_duplex_ifc_pdf | consistency | residential_duplex | missing | FAIL | FAIL |
| cross_clinic_pdf | consistency | healthcare_clinic | missing | FAIL | FAIL |
| cross_office_pdf | consistency | office | missing | FAIL | FAIL |

## Phase 1

See `reports/phase1_metrics.csv`. Per-subsystem scores come from `CompletenessScorer` / `BuildingMetadata` plus CV-only proxies when reference geometry exists.

## Phase 2

See `reports/phase2_metrics.csv`. Derived from `StructuralEngine` outputs.

## Robustness

Synthetic degradations are applied to a single reference plan (`reports/benchmark_cache/`). See `robustness_metrics.csv`.

## Consistency (cross-input)

- **IFC office vs synthetic raster**: Δcompleteness=0.0, ΔP1 conf=0.0, ΔP2 conf=0.0795.
  - Different input modalities and scales are not expected to match numerically; structural equivalence requires human review.

## Trustworthiness

- **confidence_vs_degradation**: partial — Structured/IFC confidence is driven by completeness scorer, not input SNR; CV raster shows variable completeness across degradations — see robustness_metrics.csv.
- **warnings_vs_evidence**: partial — Completeness scorer appends missing_field warnings; CV path does not uniformly add degradation-specific warnings (gap).
- **llm_budget_enforcement**: not_exercised — ReconciliationBudget exists but is not invoked from CVPipeline; budget metrics are zero / N/A.
- **high_confidence_nonsense_guard**: manual_review_required — No automated check prevents high Phase 2 confidence when span_map is irregular; flagged in structural_sanity_notes when triggered.

## Top 5 weaknesses (evidence-based)

1. **Cross-input PDF/raster assets missing** — duplex, clinic, and office PDF comparisons cannot be executed; see unresolved cases in `case_results.csv`.
2. **LLM reconciliation not exercised in CV path** — `ReconciliationBudget` metrics stay at zero; degraded plans are not LLM-reconciled in this benchmark run.
3. **Ground-truth metrics only on synthetic rasters** — wall IoU / OCR accuracy are not defined for IFC-only or structured-only cases.
4. **CAD metadata confidence is static** — `from_cad_data` assigns coarse fixed confidence scores (not evidence-weighted per file quality).
5. **Human-review triggers are completeness-driven** — few degradation-specific warnings are emitted automatically for noisy scans.

## Top 5 strongest behaviors observed

1. **Structured form path is deterministic** — happy-path structured cases complete Phase 1 and Phase 2 without exceptions.
2. **IFC samples in `data/` parse end-to-end** when `ifcopenshell` is available — full graph + structural engine run.
3. **DXF synthetic baseline** — parser + `from_cad_data` + structural engine completes on the generated test plan.
4. **Phase 2 always emits constraints and candidates** for successful Phase 1 graphs (non-zero constraint lists in metrics).
5. **Forbidden-region classification** — supports inside forbidden polygons are labeled `FORBIDDEN` (see Phase 2 metrics).

## Recommended next fix (prioritized)

1. **Add real PDF/raster fixtures** for office, duplex, and clinic, with shared ground truth, to enable true cross-input consistency and OCR/grid evaluation.

## Interpretation of failures

Failures are dominated by **missing benchmark assets** and **benchmark limitations** (LLM path not wired), not by random pipeline crashes — see `failure_analysis.md`.