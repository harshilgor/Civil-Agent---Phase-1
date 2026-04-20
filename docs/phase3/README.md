# Phase 3 — Load & Assumption Engine

Phase 3 of Civil Agent converts the Phase 1 **Building Graph** and the Phase 2
**Structural Design Graph** into a fully specified **Design Load Model** plus
a transparent **Assumption Register**, per ASCE 7-22. Every computed value is
traceable to a code provision or an explicit engineering rationale; every
numeric assumption is recorded and can be overridden by the user.

---

## What Phase 3 does

1. Reads a Building Graph (geometry, stories, occupancy, facade) and a
   Structural Design Graph (support candidates, zones, system candidates).
2. Computes dead loads, unreduced live loads, per-support tributary areas
   (Voronoi cells clipped to the facade polygon), and story-by-story
   aggregated gravity loads.
3. Computes simplified wind pressures and story forces per ASCE 7-22 Chapter
   27 (Directional Procedure, simplified).
4. Computes seismic base shear and story forces per ASCE 7-22 Chapter 12
   (Equivalent Lateral Force).
5. Evaluates all seven LRFD load combinations per ASCE 7-22 Section 2.3.1 and
   flags the governing combination at each support.
6. Returns a `DesignLoadModel` (for Phase 4) and an `AssumptionRegister`.

## What Phase 3 does NOT do

- It does **not** size members (no beam / column section selection).
- It does **not** run finite-element analysis or detailed serviceability
  checks.
- It does **not** support non-rectangular or highly irregular buildings —
  those cases still run but emit warnings (`P3W002`, `P3W003`).
- It supports **only ASCE 7-22** in V1. Any other building code returns
  `status: "failed"` with `P3W008`.

---

## Inputs and outputs

| Input field | Source |
|---|---|
| `building_graph` | Phase 1 (BuildingGraph as dict) |
| `structural_design_graph` | Phase 2 (StructuralDesignGraph as dict) |
| `location` | user / frontend |
| `material_family` | user / frontend (`reinforced_concrete` or `structural_steel`) |
| `risk_category` | ASCE 7-22 Table 1.5-1 |
| `exposure_category` | ASCE 7-22 Section 26.7 (`B`, `C`, `D`) |
| `basic_wind_speed_m_per_s` | optional, defaults to 40 m/s |
| `site_class` | ASCE 7-22 Chapter 20, default `"D"` |
| `Ss` / `S1` | ASCE 7 Hazard Tool or defaults |
| `overrides` | `list[OverrideEntry]` |

| Output field | Shape |
|---|---|
| `status` | `"success" \| "partial" \| "failed"` |
| `design_load_model` | `DesignLoadModel` — see `src/phase3/models/outputs.py` |
| `assumption_register` | `AssumptionRegister` |
| `warnings` | `list[Phase3Warning]` |
| `overall_confidence` | `float` (0.10 – 1.00) |
| `processing_time_seconds` | wall-clock time |

---

## Building code scope

**V1 targets ASCE 7-22 only.** No other code is supported; if `building_code`
in the input is not exactly `"ASCE 7-22"`, Phase 3 returns a failed status
with warning `P3W008`. The following ASCE 7-22 sections are referenced in the
implementation:

- Chapter 3 and Table C3.1-1 — dead loads and material unit weights
- Chapter 4 (Table 4.3-1, Section 4.7.3) — live loads and reduction
- Chapter 12 (Section 12.8) — ELF seismic procedure
- Chapter 27 (Section 26.7, 26.10, 26.11, Figure 27.3-1) — simplified wind
- Section 2.3.1 — LRFD strength combinations
- Tables 1.5-1 / 1.5-2 — risk category and importance factors

---

## How to run locally

### 1. Generate the sample inputs

```bash
python scripts/generate_phase3_samples.py
```

This writes three samples into `data/samples/phase3/`.

### 2. Run Phase 3 from Python

```python
import json
from pathlib import Path
from src.phase3.models.inputs import Phase3Input
from src.phase3.phase3_service import Phase3Service

payload = json.loads(Path("data/samples/phase3/sample_input_office_rc.json").read_text())
phase3_input = Phase3Input(**payload)
output = Phase3Service().run(phase3_input)

print(output.status, output.overall_confidence)
print(f"{len(output.assumption_register.records)} assumptions recorded")
```

### 3. Run Phase 3 over HTTP

Start the API:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Then:

```bash
curl -X POST http://localhost:8000/api/v1/phase3/compute \
  -H "Content-Type: application/json" \
  -d @data/samples/phase3/sample_input_office_rc.json
```

Health check:

```bash
curl http://localhost:8000/api/v1/phase3/health
```

---

## How to run the tests

```bash
pytest tests/test_phase3/ -v
```

All 49 Phase 3 tests are independent and run in under 1 second.

---

## The Assumption Register

Every numeric default, table lookup, material property, and engineering
judgement made by Phase 3 is recorded as an `AssumptionRecord`:

```json
{
  "id": "slab_self_weight_rc",
  "name": "RC slab self-weight",
  "value": 4.8,
  "unit": "kPa",
  "source": "ASCE 7-22 Table C3.1-1 x slab thickness",
  "confidence": 0.9,
  "confidence_level": "high",
  "rationale": "Self-weight = 0.2 m x 24 kN/m^3 = 4.80 kPa for a 200 mm RC flat slab.",
  "overrideable": true,
  "was_overridden": false,
  "affects_modules": ["dead_load", "story_loads", "seismic"]
}
```

Sample runs produce **130–220 assumptions** (depending on building size and
support count). The register reports:

- `total_count`
- `overridden_count`
- `low_confidence_count` (confidence < 0.60)

---

## The override mechanism

To override an assumption through the API, post to `/phase3/override/{task_id}`:

```bash
curl -X POST http://localhost:8000/api/v1/phase3/override/<task_id> \
  -H "Content-Type: application/json" \
  -d '[
    {
      "assumption_id": "superimposed_dead_load",
      "new_value": 2.0,
      "provided_by": "engineer@firm.com",
      "justification": "Stone floor finish on level 3"
    }
  ]'
```

The service re-runs Phase 3 with overrides merged into the assumption
builder. Non-overrideable assumptions (e.g. LRFD combination factors) raise
an error surfaced as a warning.

Programmatic usage:

```python
from src.phase3.models.inputs import OverrideEntry

updated = Phase3Service().rerun_with_overrides(
    phase3_input,
    [OverrideEntry(assumption_id="basic_wind_speed", new_value=50.0)],
)
```

---

## Known limitations (V1)

- Single structural system per material family by default. Use overrides for
  R / Cd / Ω₀ when a non-default system is desired.
- No snow (S) or rain (R) loads — treated as zero in LRFD combinations.
- Wind procedure is the simplified Directional Procedure for rectangular
  buildings ≤ 60 m tall; out-of-envelope buildings still return a result but
  with warning `P3W001`.
- Seismic procedure is ELF only; modal and response-history procedures are
  out of scope.
- Tributary fallback (equal area division) triggers if a story has fewer
  than 3 support candidates or if the Voronoi computation fails on the given
  geometry.

---

## Downstream consumers

**Phase 4 — Candidate Design Generator** consumes:

- `DesignLoadModel.dead_loads`, `live_loads`, `wind_loads`, `seismic_loads`
- `DesignLoadModel.load_combinations` (governing combination flag)
- `DesignLoadModel.member_demands` (per-support axial demands + cumulative)
- `AssumptionRegister` for traceability in the candidate justification
  payload

Phase 4 should never silently override a Phase 3 assumption — if it needs a
different value, it must post an `OverrideEntry` via
`/phase3/override/{task_id}` so the change is auditable end to end.
