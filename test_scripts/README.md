# Phase 1 Smoke Tests

These scripts validate **model code + weight loading** for Stage-1 adapters.

## Run

```bash
python test_scripts/test_cubicasa.py
python test_scripts/test_deepfloorplan.py
python test_scripts/test_raster_to_graph.py
python test_scripts/test_roomformer.py
python test_scripts/test_polyroom.py
```

Each script prints diagnostics JSON and then `PASS` / `FAIL`.

## Current expected state

- `cubicasa`: should pass once `vendors/cubicasa/floortrans` and checkpoint file exist.
- `deepfloorplan`: should pass once `vendors/tf2_deepfloorplan/dfp` and `weights/log/` exist.
- `raster_to_graph`: fails until gated pretrained weights are added.
- `roomformer`: fails until `roomformer_stru3d.pth` is added.
- `polyroom`: fails until checkpoints are added.
