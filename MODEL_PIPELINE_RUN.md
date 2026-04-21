# Single-Model Pipeline Run (Any Model Branch)

Use this on any of the model branches:

- `model/cubicasa`
- `model/deepfloorplan`
- `model/polyroom`
- `model/raster_to_graph`
- `model/roomformer`

The active model for the checked-out branch is stored in `config/active_model.txt`.

## Input -> model -> output

From repo root, run:

```bash
python test_scripts/run_sample_model_tester.py --image sample_model_tester_img.png
```

The runner now defaults to the active branch model from `config/active_model.txt`.
If you want to override, use:

```bash
python test_scripts/run_sample_model_tester.py --image sample_model_tester_img.png --models <active_model>
```

- Input image: `sample_model_tester_img.png`
- Model executed: `<active_model>`
- Output root: `test_scripts/outputs/sample_model_tester/`

## Saved outputs (all branches)

- `test_scripts/outputs/sample_model_tester/summary.json`
- `test_scripts/outputs/sample_model_tester/<active_model>/result.json`

If model weights are missing or inference is not wired yet, the run fails with details in `result.json` (`loaded: false` or `predicted: false` plus `error`/`traceback`).

## Model-specific artifacts

- `cubicasa`
  - `test_scripts/outputs/sample_model_tester/cubicasa/rooms.png`
  - `test_scripts/outputs/sample_model_tester/cubicasa/walls.png`
- `deepfloorplan`
  - `test_scripts/outputs/sample_model_tester/deepfloorplan/rooms.png`
  - `test_scripts/outputs/sample_model_tester/deepfloorplan/boundaries.png`
- `roomformer`
  - `test_scripts/outputs/sample_model_tester/roomformer/density_map.png`
  - `test_scripts/outputs/sample_model_tester/roomformer/polygons_overlay.png`
- `polyroom`
  - output directory: `test_scripts/outputs/sample_model_tester/polyroom/`
  - see `result.json` for produced artifacts or metadata
- `raster_to_graph`
  - output directory: `test_scripts/outputs/sample_model_tester/raster_to_graph/`
  - see `result.json` for produced artifacts or metadata

## Branch-active runtime output path

For active-branch single-model runs (non-sample runner), outputs are written under:

- `data/single_model_outputs/<run_id>/`
