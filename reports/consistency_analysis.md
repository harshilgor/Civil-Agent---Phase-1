# Consistency analysis

The benchmark **does not** claim metric equivalence between IFC exports and raster inference without shared scale registration and ground truth.

## Available comparison

- IFC office vs synthetic raster: see deltas in JSON below.

```json
[
  {
    "pair": "IFC office vs synthetic raster",
    "a_case": "ifc_office_s",
    "b_case": "raster_office_clean",
    "completeness_delta": 0.0,
    "p1_confidence_delta": 0.0,
    "p2_confidence_delta": 0.0795,
    "notes": "Different input modalities and scales are not expected to match numerically; structural equivalence requires human review."
  }
]
```

## Proxy comparison (IFC office vs synthetic raster)

- IFC `completeness`=0.84 vs raster `completeness`=0.84 (not comparable numerically — different graph construction rules).

## Unresolved required cross-input cases

- `cross_duplex_ifc_pdf`, `cross_clinic_pdf`, `cross_office_pdf` — documented as missing inputs.