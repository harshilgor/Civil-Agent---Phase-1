# Civil Agent — Technical Brief for Implementation

> **Purpose of this document:** This is the complete technical ground truth for an AI coding agent building Civil Agent Phase 1. It covers the full-stack architecture: ML pipeline, backend API, frontend application, data schemas, model integration details, and known constraints. Every implementation decision should be traceable to this document.

---

## System Architecture Overview

Civil Agent is a three-tier application:

1. **Frontend** — React/TypeScript SPA with a canvas-based floor plan viewer and editing workspace.
2. **Backend API** — FastAPI (Python) serving REST endpoints and WebSocket connections for real-time pipeline progress.
3. **ML Pipeline Worker** — Async worker (Celery or similar) that runs the multi-model perception + fusion + geometry pipeline on GPU.

The pipeline is the core IP. It takes a floor plan image and produces structured room/wall data through four stages plus a scale extraction interstitial. It operates in two modes (Light and Deep) that share the same stages but differ in model count and fusion complexity.

---

## Repository Structure

```
civil-agent/
├── config/
│   ├── pipeline.yaml              # Mode, resolution, thresholds, stage toggles
│   ├── models.yaml                # Per-model: vendor path, weight path, trust weight,
│   │                              #   framework (pytorch/tensorflow), input spec, output spec
│   └── scale.yaml                 # Scale extraction: OCR params, fallback hierarchy
│
├── vendors/                       # Vendored external model repos (pinned, adapted)
│   ├── cubicasa/                  # PyTorch 1.0→modern; floortrans package + weights (.pkl)
│   ├── tf2_deepfloorplan/         # TensorFlow 2; dfp package + weights (log/store/G)
│   ├── roomformer/                # PyTorch 1.9; DETR-like arch + checkpoints (.pth)
│   ├── polyroom/                  # PyTorch; requires Mask2Former + PolyRoom checkpoints
│   ├── raster_to_graph/           # PyTorch 3.7; autoregressive transformer + weights
│   └── floorplan_transformation/  # PyTorch port (untested) of Torch7 original + weights
│
├── backend/
│   ├── api/                       # FastAPI routes, WebSocket, middleware
│   ├── worker/                    # Celery task runner, GPU manager
│   ├── services/                  # Job, edit, quantity, export business logic
│   ├── storage/                   # Job store, result store, image store
│   └── pipeline/                  # The ML pipeline (stages 0–4)
│       ├── core/                  #   Schemas, registry, config
│       ├── stage0_input/          #   Normalization
│       ├── stage1_perception/     #   Model adapters + orchestrator
│       ├── stage1_5_scale/        #   Scale extraction
│       ├── stage2_fusion/         #   Light and deep fusion
│       ├── stage3_geometry/       #   Topology repair
│       ├── stage4_output/         #   Final serialization
│       └── pipeline.py            #   Top-level orchestrator
│
├── frontend/
│   ├── src/
│   │   ├── app/                   # Root layout, routes, providers
│   │   ├── api/                   # Typed HTTP client, WebSocket manager, TS types
│   │   ├── pages/                 # Upload, Processing, Viewer pages
│   │   ├── canvas/                # Core: layers, interactions, renderer, coordinate math
│   │   ├── panels/                # Inspector, Quantity, Layer, Diagnostics, Scale panels
│   │   ├── toolbar/               # Mode switcher, undo/redo, export, confidence filter
│   │   ├── state/                 # Zustand stores: job, canvas, selection, edit, quantity
│   │   ├── hooks/                 # useJob, useCanvasInteraction, useRoomEdit, useQuantities
│   │   └── shared/                # Reusable components
│   └── tests/
│
├── docker/
│   ├── Dockerfile.api             # FastAPI
│   ├── Dockerfile.worker          # Pipeline worker (GPU, PyTorch)
│   ├── Dockerfile.tensorflow      # DeepFloorplan isolation
│   ├── Dockerfile.frontend        # Node build + nginx
│   └── docker-compose.yaml        # Full stack orchestration
│
├── scripts/
│   ├── setup_vendors.sh           # Clone repos, download weights, verify checksums
│   └── run_pipeline.py            # CLI entry point for pipeline-only testing
│
└── requirements/
    ├── api.txt                    # FastAPI, uvicorn, celery, redis, sqlalchemy
    ├── pytorch.txt                # torch, torchvision, opencv, numpy, scipy, shapely
    └── tensorflow.txt             # tensorflow, opencv (isolated)
```

---

## ML Pipeline: Stage-by-Stage Specification

### Stage 0: Input Normalization

**Module:** `backend/pipeline/stage0_input/`

**Input:** Raw file bytes (PNG/JPG/PDF) + format string.

**Processing:**
1. PDF → rasterize first page at 150 DPI using pymupdf or pdf2image.
2. Resize to configurable target resolution. NOTE: Do NOT hardcode 512×512. CubiCasa was fine-tuned at original resolution (varies), DeepFloorplan uses 512×512, RoomFormer uses 256×256. Stage 0 produces a normalized base tensor; each model adapter handles its own final resize.
3. CLAHE contrast normalization.
4. Produce both RGB (H×W×3, uint8) and grayscale (H×W, uint8) copies.
5. Optional Hough-line-based deskew.

**Output schema — `NormalizedInput`:**
```
image_rgb:        ndarray[H, W, 3]      # uint8
image_gray:       ndarray[H, W]          # uint8
original_size:    tuple[int, int]         # (H_orig, W_orig)
target_size:      tuple[int, int]         # (H, W) after resize
source_format:    str                     # "png" | "jpg" | "pdf"
deskew_applied:   bool
```

---

### Stage 1: Perception Layer

**Module:** `backend/pipeline/stage1_perception/`

This is NOT a simple "run all models in parallel" stage. It has a dependency structure.

**Execution order:**

```
PHASE 1 (parallel, on Stage 0 output directly):
  ├── CubiCasa adapter      → ModelRoomOutput (A1) + ModelBoundaryOutput (B1)
  ├── DeepFloorplan adapter  → ModelRoomOutput (A2) + ModelBoundaryOutput (B2)
  └── Raster-to-Graph adapter → ModelBoundaryOutput (B3)

--- Deep mode only, AFTER Phase 1 boundary outputs are available ---

INTERMEDIATE STEP:
  └── Density Map Synthesizer: takes B1+B2 fused boundary → grayscale density map

PHASE 2 (sequential, Deep mode only):
  └── RoomFormer/PolyRoom adapter → ModelRoomOutput (A3) with polygon proposals
      (input: synthesized density map, NOT original floor plan image)
```

**Why the dependency exists:** RoomFormer and PolyRoom were trained on density maps derived from 3D point clouds, NOT on architectural floor plan images. They cannot consume the Stage 0 RGB output directly. The density map synthesizer converts boundary detection results into a format these models understand.

#### Model Adapter Details

Each adapter follows a common interface:

```python
class BaseAdapter:
    def load(self, config: ModelConfig) -> None: ...
    def predict(self, input: NormalizedInput) -> None: ...
    def to_room_output(self) -> ModelRoomOutput | None: ...
    def to_boundary_output(self) -> ModelBoundaryOutput | None: ...
```

##### CubiCasa Adapter (`cubicasa_adapter.py`)

- **Source:** `vendors/cubicasa/` — vendored from `CubiCasa/CubiCasa5k` GitHub, modernized for current PyTorch.
- **Framework:** PyTorch.
- **Weights:** `model_best_val_loss_var.pkl` (downloaded via Google Drive link in original repo).
- **Input preprocessing:**
  - Takes Stage 0 RGB tensor.
  - Resizes to the model's expected size (original CubiCasa code uses variable sizes; their eval uses original resolution with RotateNTurns 4-rotation TTA).
  - Applies their `DictToTensor` transform.
- **Forward pass:** Single call to their multi-task ResNet-152 network.
- **Output parsing:** The model produces three heads simultaneously:
  - Room segmentation: 12 classes (Background, Outdoor, Wall, Kitchen, Living Room, Bedroom, Bathroom, Entry, Railing, Storage, Garage, Undefined).
  - Icon segmentation: 11 classes.
  - Junction heatmaps for wall endpoint detection.
  - Use `split_prediction()` from their `floortrans.post_prosessing` to separate room vs wall outputs.
- **Produces BOTH** `ModelRoomOutput` (from room segmentation head) AND `ModelBoundaryOutput` (from wall class in room segmentation + junction heatmaps). This is ONE model call, TWO outputs.
- **Known issues:** Original code targets Python 3.6 / PyTorch 1.0 / CUDA 9. Community fork `EmanuelKuhn/CubiCasa5k` has dependency patches. Vendored version must be modernized.

##### DeepFloorplan Adapter (`deepfloorplan_adapter.py`)

- **Source:** `vendors/tf2_deepfloorplan/` — vendored from `zcemycl/TF2DeepFloorplan` GitHub.
- **Framework:** TensorFlow 2. **THIS IS THE ONLY TF MODEL IN THE PIPELINE.** Must be isolated from PyTorch models to avoid GPU memory conflicts.
- **Isolation strategy:** Run in a separate process (subprocess or Celery task on a dedicated TF worker) and communicate via serialized numpy arrays on disk or shared memory. Alternatively, convert to ONNX and run via onnxruntime in the PyTorch process.
- **Weights:** `log/store/G` (TF checkpoint) or `model/store` (SavedModel) or `model/store/model.tflite` (TFLite).
- **Input preprocessing:**
  - Takes Stage 0 RGB tensor.
  - Resizes to 512×512.
  - Backbone options: VGG16 (default), MobileNetV1, MobileNetV2, ResNet50.
- **Forward pass:** Single call via `dfp.deploy` logic. Produces two heads simultaneously:
  - Room-type segmentation map.
  - Boundary/wall segmentation map.
- **Produces BOTH** `ModelRoomOutput` (A2) AND `ModelBoundaryOutput` (B1 in Light mode, B2 in Deep mode). ONE forward pass, TWO outputs.
- **Inference command pattern:** `python -m dfp.deploy --image input.jpg --weight log/store/G --loadmethod log --postprocess --colorize`

##### RoomFormer Adapter (`roomformer_adapter.py`)

- **Source:** `vendors/roomformer/` — vendored from `ywyue/RoomFormer` GitHub.
- **Framework:** PyTorch 1.9 / CUDA 11.1. DETR-like architecture with ResNet backbone.
- **Weights:** `checkpoints/roomformer_stru3d.pth` (pretrained on Structured3D).
- **CRITICAL INPUT MISMATCH:** RoomFormer expects a single-channel (H×W) grayscale density map produced by projecting a 3D point cloud top-down. It does NOT accept floor plan images. The `density_map_synthesizer.py` must convert boundary detection outputs into a suitable pseudo-density map.
- **Input preprocessing:**
  - Receives synthesized density map (NOT Stage 0 output).
  - Resizes to 256×256.
  - Formats as COCO-style input expected by their dataloader.
- **Output:** Variable-size set of room polygons, each as an ordered sequence of corner coordinates. Also predicts room types and optionally doors/windows.
- **Produces:** `ModelRoomOutput` (A3) with `room_polygons` populated. No boundary output.
- **Deep mode only.**

##### PolyRoom Adapter (`polyroom_adapter.py`)

- **Source:** `vendors/polyroom/` — vendored from `3dv-casia/PolyRoom` GitHub.
- **Framework:** PyTorch.
- **Weights:** Downloadable checkpoint (Mask2Former checkpoint + PolyRoom checkpoint).
- **CRITICAL: Two-model chain.** PolyRoom requires Mask2Former instance segmentation results as input to its room-aware query initialization. So inference is: (1) run Mask2Former on density map → instance masks, (2) run PolyRoom with instance masks as query init → refined polygons.
- **Same input mismatch as RoomFormer** — expects density maps, not floor plan images.
- **Produces:** `ModelRoomOutput` (A3 alternative) with `room_polygons`. No boundary output.
- **Deep mode only. Alternative to RoomFormer — pick one per deployment, not both.**

##### Raster-to-Graph Adapter (`raster_to_graph_adapter.py`)

- **Source:** `vendors/raster_to_graph/` — vendored from `SizheHu/Raster-to-Graph` GitHub.
- **Framework:** PyTorch 3.7 / CUDA 11.1.
- **Weights:** Provided in repo (trained on LIFULL dataset, 10,000+ real residential floor plans).
- **Input:** Raster floor plan image — this model CAN consume floor plan images directly. However, the authors warn that images must be preprocessed to match their training data style. If your floor plans look very different from Japanese residential plans, accuracy will degrade and retraining may be needed.
- **Input preprocessing:**
  - Takes Stage 0 RGB image.
  - Applies their specific preprocessing (described in their data pipeline docs).
  - Uses their `MyDataset_demo` loader.
- **Output:** Structural graph — wall junctions + wall segments in graph traversal order, with semantic labels (room types).
- **Produces:** `ModelBoundaryOutput` (B3) with `wall_vectors: list[Edge]` populated. The vectorized edges are the primary value — these feed directly into Stage 3 boundary snapping.
- **Known issues:** Developed on Windows 10; may have path separator issues on Linux. Autoregressive inference is sequential and potentially slow.
- **Deep mode only.**

##### FloorplanTransformation Adapter (`floorplan_transform_adapter.py`)

- **Source:** `vendors/floorplan_transformation/` — vendored from `art-programmer/FloorplanTransformation/pytorch/` GitHub.
- **Framework:** Originally Torch7/Lua; PyTorch port exists but is explicitly untested by authors.
- **Weights:** Pretrained for Lua version; PyTorch port weights unknown.
- **LOWEST PRIORITY. Only use as fallback if Raster-to-Graph doesn't work for your data.**
- **Output:** Wall junctions → integer programming → wall lines, door lines, icon boxes.
- **Produces:** `ModelBoundaryOutput` (B3 alternative) with `wall_vectors`.

#### Density Map Synthesizer (`density_map_synthesizer.py`)

This is a NEW module required because of the RoomFormer/PolyRoom input mismatch.

**Input:** Fused boundary map from Phase 1 models (B1 + B2, or just B1 in a simpler implementation).

**Output:** Single-channel grayscale density map (256×256) formatted to resemble a point-cloud-derived occupancy map.

**Process:**
1. Take the binary or probabilistic boundary/wall map.
2. Apply Gaussian blur to soften hard edges (mimicking point cloud density falloff).
3. Optionally invert (walls = high density, open space = low density) depending on what RoomFormer's training data looks like.
4. Resize to 256×256.
5. Normalize to [0, 1] float range.

This is an approximation. Quality will depend on how well the synthesized density map resembles actual point-cloud projections. This is an area where experimentation is needed.

---

### Stage 1.5: Scale Extraction

**Module:** `backend/pipeline/stage1_5_scale/`

Runs in parallel with or after Stage 1 (it only needs the original image, not model outputs).

**Process:**
1. `dimension_detector.py`: OCR + heuristic line detection to find dimension annotations and numeric labels.
2. `scale_bar_detector.py`: Detect scale bars, title block annotations ("1:100", "¼″ = 1′-0″").
3. `scale_resolver.py`: Cross-validate multiple detected scales (flag if > 5% contradiction), apply fallback hierarchy, produce final `ScaleResult`.

**Output schema — `ScaleResult`:**
```
scale_factor:     float | None     # pixels-to-meters
scale_confidence: str              # "high" | "moderate" | "low" | "none"
scale_source:     str              # "scale_bar" | "dimension_annotations" | "title_block" | "user_override" | "none"
warnings:         list[str]
```

---

### Stage 2: Fusion Layer

**Module:** `backend/pipeline/stage2_fusion/`

#### Model Trust Hierarchy (static weights for Phase 1)

Room segmentation trust (Deep mode):
- A3 (RoomFormer/PolyRoom): weight 0.45 — topology-aware polygons, newest architecture.
- A2 (DeepFloorplan room head): weight 0.35 — dense pixel-level, boundary-aware attention.
- A1 (CubiCasa): weight 0.20 — proven baseline, coarser.

Boundary detection trust (Deep mode):
- B2 (DeepFloorplan boundary head): weight 0.45 — purpose-built for boundaries.
- B1 (CubiCasa wall detection): weight 0.35 — solid structural priors.
- B3 (Raster-to-Graph): weight 0.20 — supplementary vectorized structure.

Weights are normalized per-task to sum to 1.0.

#### Light Mode Fusion (`light/light_fusion.py`)

Five steps:
1. `B_light = threshold(boundary_B1, τ=0.5)` then `morphological_close(kernel=3)`.
2. `R_light = argmax(room_logits_A1, axis=class)`.
3. Consistency check: for each room region, compute % of perimeter aligning with `B_light` (±3px tolerance). If < 60%, flag `low_boundary_support`. If boundary bisects room, split.
4. `regions = connected_components(R_light, constrained_by=B_light)`.
5. Scale-aware metrics: compute area/perimeter in real units if scale available.

**Output:** `FusionOutput` with `room_regions`, `final_boundary_map`, `consistency_flags`.

#### Deep Mode Fusion (`deep/`)

Five sub-stages, each producing inspectable intermediate outputs:

**Sub-stage 2.3.1 — Agreement Mapping** (`agreement.py`):
- Per-pixel room agreement: for each pixel, count model class votes, compute `agreement_score = max_vote_fraction`.
- Per-pixel boundary agreement: `mean(B1, B2>τ, B3)`. ≥0.67 = strong, 0.33 = weak, 0.0 = none.
- Output: `room_agreement_map (H×W)`, `boundary_agreement_map (H×W)`, `room_dominant_class (H×W)`.

**Sub-stage 2.3.2 — Boundary Fusion** (`boundary_fusion.py`):
- Weighted combination: `B_fused_raw = w_B1*B1 + w_B2*B2 + w_B3*B3`.
- Agreement-gated thresholding: where agreement ≥0.67, accept at τ=0.3; where agreement=0.33, accept only at τ=0.7.
- Continuity enforcement: morphological closing (kernel=5), endpoint extension (within 8px gap → connect).
- Vector candidate integration: accept B3 vectors aligning with fused boundaries (IoU>0.5), reject contradictions.
- Output: `B_fused (H×W binary)`, `B_uncertain (H×W)`, `wall_vector_priors (list[Edge])`.

**Sub-stage 2.3.3 — Room Fusion** (`room_fusion.py`):
- Weighted logit combination: `R_fused_logits = w_A1*A1 + w_A2*A2 + w_A3_raster*A3_rasterized`.
- Boundary-constrained argmax: pixels on B_fused → boundary class override.
- Polygon proposal scoring: for each A3 polygon, score = `0.4*coverage + 0.4*boundary_support + 0.2*shape_score`. >0.7 = structural_proposal, 0.4–0.7 = soft_proposal, <0.4 = discarded.
- Output: `R_fused (H×W)`, `R_fused_confidence (H×W)`, `structural_proposals`, `soft_proposals`.

**Sub-stage 2.3.4 — Cross-Task Reconciliation** (`reconciliation.py`):
Three passes:
- **Pass A (Boundary-enforced splitting):** For each R_fused connected region, if B_fused passes through interior → split along boundary. Boundaries win when `boundary_agreement ≥ 0.67`.
- **Pass B (Enclosure extraction):** Extract enclosed regions from B_fused graph. If enclosed region has room support (IoU>0.5 with R_fused) → accept. If no support → check structural_proposals → soft_proposals → mark as `unknown_region`.
- **Pass C (Region scoring):** Composite score per region = `0.25*s_room + 0.25*s_boundary + 0.20*s_polygon + 0.15*s_shape + 0.15*s_agreement`. Thresholds: ≥0.70 accept, 0.50–0.70 accept_with_warning, 0.30–0.50 merge_candidate, <0.30 reject.
- **Topology conflict protocol:** When models disagree on room count → identify contested zone → trust hierarchy as tiebreaker → if A3 topology has boundary support, accept A3 → else majority vote → else mark `topology_uncertain` and emit all proposals for user review. NEVER average across topologies.

**Sub-stage 2.3.5 — Diagnostic Assembly** (`diagnostics.py`):
Packages all intermediate outputs into `FusionDiagnostics`: agreement maps, per-model masks, contested zones, rejected regions, and the `decision_log` (per-region: models involved, agreement score, pass applied, action taken, composite score, flags, reason string).

---

### Stage 3: Geometry & Topology Repair

**Module:** `backend/pipeline/stage3_geometry/`

1. **Region extraction** (`region_extractor.py`): Convert fused boundaries → closed regions → polygons using contour detection (OpenCV `findContours`) or Shapely operations.
2. **Topology enforcement** (`topology.py`): Ensure no overlapping rooms, no leaking boundaries, one label per region. Use Shapely polygon operations for overlap detection and resolution.
3. **Split/merge** (`split_merge.py`): Split regions crossing strong walls (reference `decision_log` to avoid re-doing fusion decisions). Merge tiny regions (area < configurable threshold) into adjacent high-confidence neighbors.
4. **Boundary snapping** (`boundary_snap.py`): Align room polygon edges with wall centerlines and `wall_vector_priors` from B3. Use nearest-point snapping within a tolerance.

---

### Stage 4: Output Generation

**Module:** `backend/pipeline/stage4_output/`

Produces the final `PipelineOutput`:
```
rooms:          list[Region]           # polygon + class + area + confidence + provenance
boundaries:     ndarray[H, W]          # final binary boundary map
wall_vectors:   list[Edge]             # validated vector wall segments
scale:          ScaleResult
metadata:       PipelineMetadata       # pipeline mode, processing time, model versions
diagnostics:    FusionDiagnostics | None  # None in Light mode
```

Each `Region` contains:
```
region_id:        str
polygon:          list[tuple[float, float]]    # ordered vertices
label:            str                          # room class
area_px:          float
area_m2:          float | None                 # null if no scale
perimeter_px:     float
perimeter_m2:     float | None
composite_score:  float                        # 0.0–1.0
confidence_tier:  str                          # "high" | "needs_review" | "low_confidence"
flags:            list[str]
provenance:       RegionProvenance             # contributing_models, agreement_score,
                                               #   boundary_support, decision_path
```

---

## Backend API Specification

**Framework:** FastAPI with async support.
**Task queue:** Celery with Redis broker (for async pipeline execution).
**Database:** PostgreSQL for job metadata + structured room objects. S3-compatible or local filesystem for large blobs (images, numpy arrays, diagnostic maps).

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/upload` | Accept floor plan image + mode selection + optional scale. Create job, enqueue pipeline task, return `{job_id}`. |
| `GET` | `/api/jobs/{id}` | Poll job status: `{status: "processing"|"complete"|"failed", stage: "perception"|"fusion"|..., progress_pct: 0-100}`. |
| `GET` | `/api/jobs/{id}/results` | Full pipeline output: rooms, boundaries (as polygon list, not raw array), scale, metadata. |
| `GET` | `/api/jobs/{id}/image` | Serve the original uploaded image (for canvas base layer). |
| `GET` | `/api/jobs/{id}/diagnostics` | Deep mode only: agreement maps (as PNG overlays), decision log, contested zones. |
| `PATCH` | `/api/jobs/{id}/rooms/{room_id}` | Update room: relabel, update polygon vertices. Backend recomputes area/perimeter, revalidates topology. Returns updated room + any topology warnings. |
| `POST` | `/api/jobs/{id}/rooms/{room_id}/split` | Split a room along a provided line. Returns two new rooms. |
| `POST` | `/api/jobs/{id}/rooms/merge` | Merge two room IDs. Returns merged room. |
| `PATCH` | `/api/jobs/{id}/scale` | Override scale factor. Backend recomputes all metric quantities. Returns updated rooms. |
| `GET` | `/api/jobs/{id}/export?format=json|geojson|csv` | Export results in specified format. |
| `WS` | `/ws/jobs/{id}` | Real-time progress updates during pipeline execution. Messages: `{stage, progress_pct, message}`. |

### Edit Service Logic

When the user edits a room polygon (vertex drag, split, merge, relabel):
1. Apply the geometric change to the stored room object.
2. Recompute area and perimeter from the new polygon + current scale factor.
3. Run topology validation: check for overlaps with neighbors, check boundary alignment.
4. If topology violation detected (e.g., edit created an overlap), return a warning but still accept the edit. Do NOT block the user.
5. Return updated room object + any new flags.

---

## Frontend Specification

**Framework:** React 18+ with TypeScript.
**Bundler:** Vite.
**State management:** Zustand (lightweight, works well with canvas-heavy apps).
**Canvas rendering:** Canvas2D API for MVP; upgrade path to WebGL/PixiJS for performance with large plans.
**Styling:** Tailwind CSS.

### Canvas Architecture

The canvas is the core UI element. It renders multiple layers in z-order:

```
Z-order (bottom to top):
  1. ImageLayer          — original floor plan image, rasterized
  2. BoundaryLayer       — wall/boundary segments as lines
  3. RoomPolygonLayer    — room polygons as filled semi-transparent shapes
  4. ConfidenceHeatmap   — optional overlay (Deep mode agreement map)
  5. ContestedZoneLayer  — optional overlay (Deep mode contested zones)
  6. EditOverlay         — vertex handles, split preview lines (only during editing)
```

**Interaction modes** (mutually exclusive, selected via toolbar):
- **Select mode:** Click to select room/wall. Hover shows tooltip with label + area. Click shows full properties in inspector.
- **Edit Vertices mode:** Selected room's vertices become draggable handles. Drag to reshape. On release, send PATCH to backend.
- **Split mode:** Click to draw a line across a selected room. On confirm, send split request to backend.
- **Merge mode:** Click two adjacent rooms. On confirm, send merge request to backend.

**Viewport:** Pan (click-drag on empty canvas or middle-mouse), zoom (scroll wheel / pinch). All coordinates must transform correctly between screen pixels, canvas pixels, and real-world units (when scale is available).

### State Stores

- **jobStore:** Current job ID, status, pipeline results (rooms, boundaries, scale, diagnostics).
- **canvasStore:** Viewport transform (offset, zoom), active layers, interaction mode.
- **selectionStore:** Currently selected room/wall IDs.
- **editStore:** Edit history stack for undo/redo. Each entry: `{action, before, after}`.
- **quantityStore:** Derived quantities (total area, per-room areas). Recomputed reactively when rooms change.

### Key Frontend Behaviors

1. **Progressive loading:** When pipeline results arrive, render immediately. Don't wait for all panels to be ready before showing the canvas.
2. **Optimistic updates:** When user edits a polygon, update the canvas immediately. Send PATCH to backend. If backend returns a topology warning, show it as a non-blocking notification.
3. **Quantity reactivity:** When any room polygon changes (edit, split, merge, relabel), recompute quantities client-side for instant feedback. Backend recomputation is the source of truth but the frontend preview is fine for responsiveness.
4. **Confidence coloring:** Default room fill colors map to confidence tier. User can toggle between confidence coloring and room-type coloring.
5. **Deep mode diagnostics:** Only rendered when user explicitly toggles them on. Agreement heatmaps are fetched as PNG overlays from the backend and rendered as semi-transparent canvas layers.

---

## Data Flow Summary

```
User uploads image
  → POST /api/upload
  → Backend creates job, enqueues Celery task
  → Worker picks up task, runs pipeline:
      Stage 0: normalize image
      Stage 1 Phase 1: CubiCasa + DeepFloorplan + Raster-to-Graph (parallel)
      Stage 1.5: Scale extraction (parallel with Stage 1)
      Stage 1 Phase 2: density map synthesis → RoomFormer/PolyRoom (Deep only)
      Stage 2: Fusion (light or deep)
      Stage 3: Geometry repair
      Stage 4: Output generation
  → Worker stores results, updates job status
  → WebSocket pushes completion event to frontend
  → Frontend fetches GET /api/jobs/{id}/results
  → Canvas renders room polygons + boundaries on original image
  → User inspects, edits, exports
```

---

## Key Technical Constraints and Gotchas

1. **TensorFlow/PyTorch isolation.** DeepFloorplan (TF2) and all other models (PyTorch) cannot share a GPU process without careful management. Best approach: run DeepFloorplan in a separate subprocess or container. Communicate via numpy arrays serialized to disk or shared memory.

2. **RoomFormer/PolyRoom cannot run in parallel with other perception models.** They need boundary outputs as input (via density map synthesis). This makes the "parallel perception" assumption from the original architecture partially incorrect. The perception orchestrator must enforce this ordering.

3. **CubiCasa and DeepFloorplan are each ONE model with TWO outputs.** Do not instantiate them twice. One forward pass produces both room and boundary results. The adapter splits the output.

4. **No model has a pip-installable library.** Every model is cloned-repo + downloaded-weights. The `vendors/` directory must be treated as vendored code with pinned versions. `scripts/setup_vendors.sh` must automate setup.

5. **Model input sizes differ.** CubiCasa: variable (original resolution preferred). DeepFloorplan: 512×512. RoomFormer: 256×256. Raster-to-Graph: depends on their preprocessing. Stage 0 normalizes once; each adapter handles its own final resize.

6. **Topology is non-negotiable.** The pipeline's output MUST have no overlapping rooms and no leaking boundaries. Stage 3 enforces this. User edits that violate topology should warn but not block.

7. **Scale may not exist.** All quantity computations must gracefully handle `scale_factor = None`. The frontend must show pixel-unit quantities with a clear warning in this case.

8. **FloorplanTransformation is last resort.** Its PyTorch port is untested by the original authors. Use Raster-to-Graph as the primary B3 model. Only fall back to FloorplanTransformation if Raster-to-Graph fails on your data.

9. **Raster-to-Graph may need retraining.** It was trained on LIFULL (Japanese residential plans). If your target floor plans are stylistically different, expect degraded accuracy. The authors explicitly warn about this.

10. **Phase 1 uses rule-based fusion only.** Do not implement learned fusion (the "small CNN/U-Net over stacked logits" mentioned in the architecture doc). That is future scope. All fusion logic is deterministic with configurable weights and thresholds.

---

## Configuration Reference

### pipeline.yaml
```yaml
mode: "light"                    # "light" | "deep"
input:
  target_resolution: [512, 512]  # Stage 0 normalization target (models resize further)
  deskew_enabled: true
  contrast_method: "clahe"       # "clahe" | "histogram_eq" | "none"
  pdf_dpi: 150
perception:
  a3_model: "roomformer"         # "roomformer" | "polyroom"
  b3_model: "raster_to_graph"    # "raster_to_graph" | "floorplan_transformation"
fusion:
  light:
    boundary_threshold: 0.5
    morphology_kernel: 3
    perimeter_alignment_threshold: 0.6
  deep:
    boundary_agreement_strong: 0.67
    boundary_low_threshold: 0.3
    boundary_high_threshold: 0.7
    morphology_kernel: 5
    endpoint_extension_px: 8
    polygon_score_accept: 0.7
    polygon_score_soft: 0.4
    composite_accept: 0.70
    composite_warning: 0.50
    composite_merge: 0.30
geometry:
  min_region_area_px: 100        # Regions smaller than this get merged
  snap_tolerance_px: 5           # Boundary snapping tolerance
```

### models.yaml
```yaml
cubicasa:
  vendor_path: "vendors/cubicasa"
  weight_path: "vendors/cubicasa/weights/model_best_val_loss_var.pkl"
  framework: "pytorch"
  trust_weight_room: 0.20
  trust_weight_boundary: 0.35
  roles: ["A1", "B1"]

deepfloorplan:
  vendor_path: "vendors/tf2_deepfloorplan"
  weight_path: "vendors/tf2_deepfloorplan/weights/log/store/G"
  framework: "tensorflow"
  load_method: "log"
  backbone: "vgg16"
  trust_weight_room: 0.35
  trust_weight_boundary: 0.45
  roles_light: ["A1_room_unused", "B1"]   # Light: only boundary head used
  roles_deep: ["A2", "B2"]

roomformer:
  vendor_path: "vendors/roomformer"
  weight_path: "vendors/roomformer/checkpoints/roomformer_stru3d.pth"
  framework: "pytorch"
  trust_weight_room: 0.45
  input_size: [256, 256]
  requires_density_map: true
  roles: ["A3"]

raster_to_graph:
  vendor_path: "vendors/raster_to_graph"
  weight_path: "vendors/raster_to_graph/weights/"
  framework: "pytorch"
  trust_weight_boundary: 0.20
  roles: ["B3"]
```

---

## Testing Strategy

**Unit tests:** Per-adapter (mock model weights, verify I/O schema compliance), per-fusion-substage (synthetic agreement maps, verify threshold logic), per-geometry-operation (known polygons, verify split/merge/snap).

**Integration tests:** End-to-end light pipeline with fixture floor plan images. End-to-end deep pipeline. API route tests with mock pipeline results.

**Frontend tests:** Canvas rendering (snapshot tests for layer compositing), interaction tests (simulated click/drag events), panel tests (correct display of room properties, quantity calculations).

**Fixture data:** A set of 5–10 sample floor plans of varying complexity (simple rectangular, L-shaped, multi-room residential, complex commercial). Each should have manually verified expected outputs for regression testing.