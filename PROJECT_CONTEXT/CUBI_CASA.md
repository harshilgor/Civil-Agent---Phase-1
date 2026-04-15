# CubiCasa Model Loading Walkthrough (From Zero)

This document explains, in detail, how this project **really loads and uses the model** for floor plan inference.

---

## 1) Short direct answers first

### What is the model called?

There are three names used at different layers:

1. **Architecture constructor name**: `hg_furukawa_original`
2. **API wrapper class**: `CubiCasaModel`
3. **Health endpoint display label**: `cubicasa_trained`

The actual neural net architecture instantiated in code is `hg_furukawa_original`.

### What weights/checkpoint file is loaded?

By default:

- `weights/model_best_val_loss_var.pkl`

This is controlled by env var:

- `FLOORPLAN_WEIGHTS_PATH`

### Where does loading happen?

Primary (current FastAPI path):

- `measurement_api/main.py` -> startup lifespan -> `CubiCasaModel(...)`
- `measurement_api/models/cubicasa_infer.py` -> `_load_model(...)`

Legacy (Flask compatibility path):

- `model_server.py` -> `load_model(...)` from `floor_plan_ml.py`

---

## 2) Big picture: exact runtime flow

### Flow A (current main service)

1. App starts (`measurement_api/main.py`).
2. Startup lifecycle (`lifespan`) creates one `CubiCasaModel`.
3. `CubiCasaModel`:
   - resolves device (`cpu`, `cuda`, or `auto`)
   - builds architecture `get_model("hg_furukawa_original", 51)`
   - rewires final heads for 44 channels
   - loads checkpoint with `torch.load(...)`
   - loads model parameters using `model.load_state_dict(checkpoint["model_state"])`
   - switches to eval mode
4. API request comes in (`/api/infer-plan`, `/api/measure-plan`, or `/analyze`).
5. Uploaded file is stored to temp path.
6. Image/PDF is loaded as `PIL.Image`.
7. `model.run_inference(...)` is called.
8. Input tensor is prepared (mode-dependent), model runs forward pass (with optional TTA rotations).
9. Output channels are split into heatmaps/rooms/icons.
10. `argmax` gives room/icon class masks.
11. Masks are restored to original image size.
12. Pipeline continues into wall extraction, OCR, scale, geometry, and response payload.

### Flow B (legacy Flask service)

1. `model_server.py` imports `load_model` from `floor_plan_ml.py`.
2. `MODEL = load_model(...)` is executed once at startup.
3. `/analyze` endpoint receives upload, saves temp image.
4. `floor_plan_to_civil_agent_brief(...)` runs full inference+postprocess path.
5. Response includes brief/geometry/masks/visualizations.

---

## 3) The model loading code path, line-by-line logic

## 3.1 Startup object creation

In `measurement_api/main.py`, the FastAPI lifespan hook does:

- read env vars:
  - `FLOORPLAN_WEIGHTS_PATH` (default `weights/model_best_val_loss_var.pkl`)
  - `FLOORPLAN_INFERENCE_MODE` (default `cubicasa`)
  - `FLOORPLAN_DEVICE` (default `cpu`)
- instantiate:
  - `CubiCasaModel(weights_path=..., device=..., inference_mode=...)`

That object is stored in `app.state.model`, then endpoints use the same singleton model for requests.

## 3.2 Architecture creation

In `measurement_api/models/cubicasa_infer.py`, `_load_model(...)` does:

1. `model = get_model("hg_furukawa_original", 51)`
2. Replace segmentation head:
   - `model.conv4_ = Conv2d(256 -> 44, kernel_size=1)`
   - `model.upsample = ConvTranspose2d(44 -> 44, kernel_size=4, stride=4)`

Why this matters:

- The network outputs channels for multi-task prediction.
- Here output channels are aligned with expected CubiCasa output layout:
  - 21 heatmaps
  - 12 room classes
  - 11 icon classes
  - total 44 channels

## 3.3 Checkpoint load and weight assignment

Still in `_load_model(...)`:

1. Validate path exists. If not, raise `FileNotFoundError`.
2. Load checkpoint:
   - `checkpoint = torch.load(path, map_location=device, weights_only=False)`
3. Read parameter state dict from:
   - `checkpoint["model_state"]`
4. Apply parameters:
   - `model.load_state_dict(checkpoint["model_state"])`
5. Send model to selected device:
   - `model.to(self.device)`
6. Set eval mode:
   - `model.eval()`

This is the crucial proof point: if checkpoint schema or tensor shapes were wrong, `load_state_dict` would fail immediately.

---

## 4) What proves it is actually loaded (not just "configured")

You have several concrete proofs in this repository.

## 4.1 Startup logs (legacy server)

`model_server.out.log` contains:

- `Initializing AI Model Server ...`
- `Model successfully loaded into VRAM.`

If loading failed, code path sets `MODEL = None` and health/analyze would fail.

## 4.2 Health endpoint behavior

FastAPI `/health` returns:

- `status: "ready"` only if `app.state.model` exists
- `device`: derived from `next(model.model.parameters()).device`
- `weights_path`: active path
- `default_inference_mode`

If model is missing, status flips to `"error"` and routes return 503.

## 4.3 End-to-end tests

`tests/test_measurement_api.py` proves real inference executes:

- Creates `CubiCasaModel(...)`
- Calls `run_inference(...)`
- Verifies mask shapes equal input image dimensions
- Exercises `/api/infer-plan`, `/api/measure-plan`, and `/analyze`

If model failed to load or run, these tests would fail.

---

## 5) How input is given to the model

This is commonly where second projects break, so here is the exact chain.

## 5.1 Request input to temp file

In pipeline functions:

- `save_upload_to_temp(upload_file)` reads upload bytes and writes a temp file with matching suffix.

## 5.2 Temp file to image object

`load_floor_plan(path, page_index=0)`:

- If PDF: rasterize selected page using `PyMuPDF` (`fitz`) when available.
- Else: open with PIL.
- Return:
  - `PIL.Image` in RGB mode
  - metadata (`source_type`, `page_index`, `size`, path)

## 5.3 Image to tensor (normalization and geometry mode)

Inside `run_inference(...)`, mode chooses preprocessing:

- `legacy`:
  - resize to square 1024x1024
  - no TTA
- `cubicasa` (default):
  - preserve aspect ratio
  - resize + pad to 1024x1024 white canvas
  - TTA enabled
- `native`:
  - keep original image size
  - TTA enabled

All modes convert image to tensor and apply:

- `tensor = tensor * 2.0 - 1.0`

That maps values from `[0, 1]` to `[-1, 1]`, matching training-time expectations.

## 5.4 Forward pass and test-time augmentation

`_run_model(...)`:

- sends input to same device as model
- runs inside `torch.no_grad()`
- if TTA enabled:
  - rotates tensor by 0/90/180/270
  - runs prediction on each
  - rotates outputs back
  - interpolates to input spatial size
  - averages predictions

## 5.5 Multi-head output split

In CubiCasa mode, it calls:

- `post_prosessing.split_prediction(output, size, [21, 12, 11])`

Meaning:

- first 21 channels: heatmaps
- next 12: room logits/probabilities
- last 11: icon logits/probabilities

Then:

- `room_mask = argmax(room_probs, axis=0)`
- `icon_mask = argmax(icon_probs, axis=0)`

## 5.6 Restore masks to original resolution

If padded mode was used:

- crop out pad margins first
- then nearest-neighbor resize back to original image shape

This is important. Without this reverse mapping, walls/rooms will be spatially misaligned downstream.

---

## 6) Why your other project might fail even if this one works

Most likely differences (in order of frequency):

1. **Wrong checkpoint schema**
   - This code expects `checkpoint["model_state"]`.
   - Some projects save as raw `state_dict`, or key names like `state_dict`.
2. **Head shape mismatch**
   - This code rewires to 44 output channels before loading.
   - If your other project leaves default head, shapes mismatch.
3. **Different preprocessing**
   - Missing `[-1,1]` normalization.
   - Missing aspect-ratio padded pipeline.
4. **Missing TTA/post-processing split**
   - If you directly argmax all channels without split logic, results degrade.
5. **Device mismatch**
   - Loading CUDA tensors on CPU without `map_location`.
6. **Incorrect image geometry restoration**
   - Not reversing padding/crop before resizing back.
7. **Wrong inference mode assumptions**
   - This repo defaults to `cubicasa`, not `legacy`.

---

## 7) Practical checklist to copy into another project

Use this exactly when porting.

1. Construct architecture:
   - `model = get_model("hg_furukawa_original", 51)`
2. Replace output heads to 44 classes:
   - `conv4_` and `upsample` as in this repo
3. Load checkpoint with map_location.
4. Confirm checkpoint contains `model_state`.
5. `model.load_state_dict(...)` with strict checking.
6. `model.to(device)` then `model.eval()`.
7. Ensure preprocessing:
   - RGB conversion
   - tensor conversion
   - `*2 - 1` normalization
   - cubicasa-style padded resize to 1024x1024
8. Run forward in `torch.no_grad()`.
9. Split channels `[21,12,11]`.
10. Argmax masks and restore to original image size.

---

## 8) Minimal debug instrumentation (high value)

Add temporary logs in your other project:

```python
print("weights path:", weights_path)
ckpt = torch.load(weights_path, map_location=device, weights_only=False)
print("checkpoint keys:", list(ckpt.keys())[:20])
print("has model_state:", "model_state" in ckpt)
print("model device before:", next(model.parameters()).device)
model.load_state_dict(ckpt["model_state"])
model.to(device).eval()
print("model device after:", next(model.parameters()).device)
```

And before first inference:

```python
print("input tensor shape:", tuple(input_tensor.shape))
print("input tensor range:", float(input_tensor.min()), float(input_tensor.max()))
out = model(input_tensor.to(device))
print("output shape:", tuple(out.shape))
```

Expected output shape pattern:

- `(batch, 44, H, W)` after final upsample.

---

## 9) How to verify live loading on this project now

## 9.1 Start FastAPI service

PowerShell example:

```powershell
$env:FLOORPLAN_WEIGHTS_PATH="weights/model_best_val_loss_var.pkl"
$env:FLOORPLAN_INFERENCE_MODE="cubicasa"
$env:FLOORPLAN_DEVICE="cpu"
python -m uvicorn measurement_api.main:app --host 0.0.0.0 --port 8000
```

Then:

```powershell
curl http://127.0.0.1:8000/health
```

You should see:

- `"status": "ready"`
- `"model": "cubicasa_trained"`
- the configured `weights_path`
- device info

## 9.2 Run direct inference endpoint

```powershell
curl -X POST http://127.0.0.1:8000/api/infer-plan `
  -F "floor_plan=@data/cubicasa5k/colorful/1012/F1_original.png" `
  -F "include_images=true" `
  -F "inference_mode=cubicasa" `
  -F "page_index=0"
```

Response should include:

- `success: true`
- `metadata.input_size`
- `metadata.model_size`
- `masks.room_mask` and `masks.icon_mask`

If model is not loaded, endpoint returns 503 with `"Model not loaded"`.

---

## 10) Architecture note: why both `51` and `44` appear

You will notice:

- constructor called with `n_classes=51`
- then head layers overwritten to `44`

This project follows that exact pattern inherited from original code paths. The effective prediction head used in inference is 44-channel after reassignment.

So when reproducing behavior, mirror the final head override, not only constructor defaults.

---

## 11) Compatibility path (legacy Flask) details

`model_server.py` still works as a direct "single-file server" path:

1. `MODEL = load_model(WEIGHTS_PATH, inference_mode=INFERENCE_MODE)`
2. `/analyze` route saves uploaded file
3. calls `floor_plan_to_civil_agent_brief(...)`
4. returns:
   - `brief`
   - `geometry`
   - debug metadata including weights path and inference mode

This is why you can also use the Flask server logs as proof that model loaded.

---

## 12) Fast failure matrix (symptom -> root cause)

- `FileNotFoundError: Model weights not found`
  - wrong `FLOORPLAN_WEIGHTS_PATH`
- `KeyError: 'model_state'`
  - checkpoint format mismatch
- `size mismatch for ...`
  - final head channel mismatch (likely not set to 44)
- `Expected all tensors to be on the same device`
  - model/input not on same device
- all-black or nonsense masks
  - preprocessing mismatch (especially normalization and mode handling)
- route returns 503 `Model not loaded`
  - startup exception prevented model creation

---

## 13) If you want a one-screen "core loader"

This is the essence you must replicate in another project:

```python
model = get_model("hg_furukawa_original", 51)
model.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1)
model.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
model.load_state_dict(checkpoint["model_state"])
model.to(device).eval()
```

And then match input pipeline and channel split exactly.

---

## 14) Final takeaways

1. Yes, this project genuinely loads CubiCasa-trained weights and runs inference.
2. The real architecture name is `hg_furukawa_original`; "CubiCasaModel" is wrapper naming.
3. The default checkpoint is `weights/model_best_val_loss_var.pkl`.
4. The most critical reproducibility points are:
   - 44-channel head override
   - `checkpoint["model_state"]`
   - cubicasa preprocess mode
   - output split `[21, 12, 11]`
   - restoring masks to original image geometry

If your other project still fails after matching this exactly, the next best diagnostic is to print checkpoint keys plus first-layer/last-layer tensor shapes in both projects and compare them side-by-side.
