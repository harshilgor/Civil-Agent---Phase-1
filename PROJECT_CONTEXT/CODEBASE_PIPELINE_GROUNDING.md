# Civil Agent Codebase-to-Pipeline Grounding Guide (Phase 1)

## Why this document exists

This is the implementation grounding map for coding agents working in this repository.
It links each existing folder and file in the skeleton to:

- product expectations from `PROJECT_CONTEXT/PRODUCT_BRIEF.md`
- technical pipeline responsibilities from `PROJECT_CONTEXT/TECHNICAL_BRIEF.md`
- current implementation status in the skeleton (implemented vs stub)

If a requested change does not map to an existing file path in this document, do not create new structure unless explicitly approved.

## Non-negotiable repository constraints

- Populate the existing skeleton; do not expand or contract structure by default.
- No new folders unless explicitly requested.
- Do not delete existing files to "simplify" architecture.
- Keep work aligned with Phase 1 scope only.
- Do not build out-of-scope features listed in `PRODUCT_BRIEF.md`.

## Canonical end-to-end pipeline (technical brief alignment)

The intended Phase 1 runtime flow is:

1. Upload file and mode selection (`light` or `deep`)
2. Stage 0 input normalization
3. Stage 1 perception (with deep-mode dependency ordering)
4. Stage 1.5 scale extraction
5. Stage 2 fusion (`light` or `deep` logic)
6. Stage 3 geometry and topology repair
7. Stage 4 output serialization
8. Frontend visualization, editing, diagnostics, and export

Everything below maps existing files to this flow.

## Repository-wide grounding map

### Root-level control files

- `.dockerignore`: container build hygiene; excludes transient/generated paths.
- `pyproject.toml`: Python packaging, dependency baseline, and pytest path config.

### Product and technical authority docs

- `PROJECT_CONTEXT/PRODUCT_BRIEF.md`: user journey, UX layers, and phase scope.
- `PROJECT_CONTEXT/TECHNICAL_BRIEF.md`: architecture, stage specs, API contracts.
- `PROJECT_CONTEXT/CODEBASE_PIPELINE_GROUNDING.md`: this file, structural mapping bible.

### Configuration

- `config/pipeline.yaml`: mode and stage threshold knobs that should drive logic.
- `config/models.yaml`: model role mapping (`A1/A2/A3`, `B1/B2/B3`) and trust weights.
- `config/scale.yaml`: scale extraction and fallback policy configuration.

### Dependency definitions

- `requirements/api.txt`: API/runtime stack.
- `requirements/pytorch.txt`: PyTorch worker stack.
- `requirements/tensorflow.txt`: isolated TensorFlow stack for DeepFloorplan.

### Orchestration and containerization

- `docker/docker-compose.yaml`: service topology (api/worker/tf-worker/frontend/datastores).
- `docker/Dockerfile.api`: API image build contract.
- `docker/Dockerfile.worker`: worker image build contract.
- `docker/Dockerfile.tensorflow`: TF isolation image build contract.
- `docker/Dockerfile.frontend`: frontend build/serve container contract.
- `docker/nginx-frontend.conf`: runtime frontend serving and proxy config.

### Scripts

- `scripts/setup_vendors.sh`: expected vendor clone + weights setup entry point (currently TODO stub).
- `scripts/run_pipeline.py`: CLI harness around backend pipeline.
- `scripts/visualize_diagnostics.py`: diagnostics visualizer entry point (currently stub).

### Vendors

- `vendors/`: expected location for vendored model repos and weights.
- Current status: folder exists but is empty; this is the largest skeleton gap vs technical brief.

## Backend grounding map

### API layer (`backend/api`)

- `backend/api/app.py`: FastAPI app composition; router + middleware wiring.
- `backend/api/deps.py`: dependency provider wiring for services/stores.
- `backend/api/websocket.py`: progress event stream contract (`/ws/jobs/{id}`).

#### Middleware

- `backend/api/middleware/cors.py`: CORS policy setup.
- `backend/api/middleware/error_handler.py`: normalized error responses.
- `backend/api/middleware/__init__.py`: package marker.

#### Route contracts

- `backend/api/routes/upload.py`: upload submission + job creation endpoint.
- `backend/api/routes/jobs.py`: job status polling endpoint.
- `backend/api/routes/results.py`: job result retrieval endpoint.
- `backend/api/routes/diagnostics.py`: deep-mode diagnostics endpoint.
- `backend/api/routes/edit.py`: room edit/split/merge endpoints.
- `backend/api/routes/scale.py`: scale override endpoint.
- `backend/api/routes/export.py`: export endpoint surface (partially stubbed).
- `backend/api/routes/__init__.py`: router package marker.

### Worker layer (`backend/worker`)

- `backend/worker/task_runner.py`: asynchronous task entry point (currently mostly stubbed logic).
- `backend/worker/gpu_manager.py`: GPU ownership and TF isolation control point.
- `backend/worker/__init__.py`: package marker.

### Services layer (`backend/services`)

- `backend/services/job_service.py`: job lifecycle transitions and status updates.
- `backend/services/edit_service.py`: edit application and topology warning policy.
- `backend/services/quantity_service.py`: area/perimeter/summary quantity logic.
- `backend/services/export_service.py`: JSON/GeoJSON/CSV export assembly.
- `backend/services/__init__.py`: package marker.

### Storage layer (`backend/storage`)

- `backend/storage/job_store.py`: job metadata storage abstraction (currently in-memory style).
- `backend/storage/result_store.py`: pipeline output persistence abstraction.
- `backend/storage/image_store.py`: uploaded image persistence abstraction.
- `backend/storage/__init__.py`: package marker.

### Pipeline root (`backend/pipeline`)

- `backend/pipeline/pipeline.py`: top-level pipeline orchestrator (currently stage chain stubbed).
- `backend/pipeline/__init__.py`: package marker.

#### Pipeline core

- `backend/pipeline/core/config.py`: typed config loading from YAML.
- `backend/pipeline/core/schemas.py`: core dataclasses/schemas across all stages.
- `backend/pipeline/core/registry.py`: adapter registration and lookup.
- `backend/pipeline/core/__init__.py`: package marker.

#### Stage 0 - input normalization (`backend/pipeline/stage0_input`)

- `backend/pipeline/stage0_input/loader.py`: format ingestion and PDF rasterization entry point (stub).
- `backend/pipeline/stage0_input/normalizer.py`: resize/CLAHE/deskew entry point (stub).
- `backend/pipeline/stage0_input/__init__.py`: package marker.

#### Stage 1 - perception (`backend/pipeline/stage1_perception`)

- `backend/pipeline/stage1_perception/base_adapter.py`: common adapter interface contract.
- `backend/pipeline/stage1_perception/perception_orchestrator.py`: execution order + deep dependency graph (stub).
- `backend/pipeline/stage1_perception/density_map_synthesizer.py`: boundary-to-density bridge for A3 models (stub).
- `backend/pipeline/stage1_perception/__init__.py`: package marker.

##### Stage 1 adapters (`backend/pipeline/stage1_perception/adapters`)

- `cubicasa_adapter.py`: A1/B1 dual-head adapter target.
- `deepfloorplan_adapter.py`: A2/B2 TensorFlow adapter target, must be isolated.
- `roomformer_adapter.py`: deep-only A3 polygon model adapter target.
- `polyroom_adapter.py`: deep-only A3 alternative adapter target.
- `raster_to_graph_adapter.py`: deep B3 wall vector adapter target.
- `floorplan_transform_adapter.py`: B3 fallback adapter target.
- `__init__.py`: adapter package marker.

#### Stage 1.5 - scale extraction (`backend/pipeline/stage1_5_scale`)

- `dimension_detector.py`: OCR and dimension text extraction entry point (stub).
- `scale_bar_detector.py`: scale bar and title block scale extraction entry point (stub).
- `scale_resolver.py`: source reconciliation and confidence assignment entry point (stub).
- `__init__.py`: package marker.

#### Stage 2 - fusion (`backend/pipeline/stage2_fusion`)

- `trust.py`: static trust weight helpers for deterministic phase-1 fusion.
- `fusion_router.py`: mode-based dispatch (`light` vs `deep`).
- `__init__.py`: package marker.

##### Stage 2 light

- `light/light_fusion.py`: threshold/morphology/consistency logic target (stub).
- `light/__init__.py`: package marker.

##### Stage 2 deep

- `deep/agreement.py`: agreement maps and dominant class computation target (stub).
- `deep/boundary_fusion.py`: weighted boundary fusion and continuity target (stub).
- `deep/room_fusion.py`: weighted room fusion and proposal scoring target (stub).
- `deep/reconciliation.py`: pass A/B/C conflict resolution target (stub).
- `deep/diagnostics.py`: diagnostics package assembly target (stub).
- `deep/__init__.py`: package marker.

#### Stage 3 - geometry and topology (`backend/pipeline/stage3_geometry`)

- `region_extractor.py`: boundary-to-region polygon extraction target (stub).
- `topology.py`: overlap/leak fixing and topology enforcement target (stub).
- `split_merge.py`: split/merge post-processing target (stub).
- `boundary_snap.py`: wall centerline snapping target (stub).
- `__init__.py`: package marker.

#### Stage 4 - output generation (`backend/pipeline/stage4_output`)

- `room_object.py`: region output object shaping.
- `metadata.py`: pipeline metadata shaping.
- `serializer.py`: final payload serialization, including export variants (partly stubbed).
- `__init__.py`: package marker.

## Frontend grounding map

### Frontend root config

- `frontend/package.json`: scripts/dependencies for React + Vite app.
- `frontend/package-lock.json`: lockfile.
- `frontend/tsconfig.json`: app TypeScript config.
- `frontend/tsconfig.node.json`: Vite/node TypeScript config.
- `frontend/vite.config.ts`: dev server + alias + test setup.
- `frontend/index.html`: SPA host shell.

### Frontend app bootstrap (`frontend/src`)

- `frontend/src/main.tsx`: app mount.
- `frontend/src/index.css`: global styling baseline.
- `frontend/src/vite-env.d.ts`: Vite typing glue.

### App composition (`frontend/src/app`)

- `App.tsx`: root app container.
- `providers.tsx`: app-wide providers.
- `routes.tsx`: upload/processing/viewer route wiring.

### API integration (`frontend/src/api`)

- `types.ts`: TypeScript API payload types mirroring backend contracts.
- `client.ts`: HTTP methods for upload/status/results/edit/export/scale.
- `websocket.ts`: progress socket connection abstraction.

### Pages (`frontend/src/pages`)

- `UploadPage/UploadPage.tsx`: upload workflow page shell.
- `UploadPage/DropZone.tsx`: drag-drop/select control.
- `ProcessingPage/ProcessingPage.tsx`: in-progress status view.
- `ViewerPage/ViewerPage.tsx`: main review/edit workspace.
- `ViewerPage/layout.ts`: viewer layout helper constants/composition.

### Canvas subsystem (`frontend/src/canvas`)

- `FloorplanCanvas.tsx`: canvas root composition and layer stack host.

#### Canvas layers

- `layers/ImageLayer.tsx`: base raster floor plan layer (currently stub text).
- `layers/BoundaryLayer.tsx`: wall/boundary vector overlay target (currently stub text).
- `layers/RoomPolygonLayer.tsx`: room polygon overlay layer.
- `layers/ConfidenceHeatmap.tsx`: deep diagnostics agreement heatmap overlay.
- `layers/ContestedZoneLayer.tsx`: contested zone overlay target (currently stub text).
- `layers/EditOverlay.tsx`: edit handles and split guides overlay.

#### Canvas interactions

- `interactions/PanZoomController.ts`: viewport pan/zoom behavior.
- `interactions/SelectionController.ts`: select/hover logic.
- `interactions/VertexDragController.ts`: vertex edit drag behavior.
- `interactions/SplitController.ts`: split line gesture behavior.
- `interactions/MergeController.ts`: multi-room merge selection behavior.

#### Canvas renderer

- `renderer/ViewportState.ts`: camera transform state model.
- `renderer/HitTestEngine.ts`: object hit-testing utilities.
- `renderer/WebGLRenderer.ts`: GPU renderer path placeholder (stub).

#### Canvas utilities

- `utils/coordinate_transform.ts`: screen/canvas/world coordinate transforms.
- `utils/polygon_math.ts`: area/perimeter and polygon helpers.
- `utils/color_scales.ts`: confidence/semantic color mapping helpers.

### Panels (`frontend/src/panels`)

#### Inspector

- `InspectorPanel/InspectorPanel.tsx`: selection-driven panel shell.
- `InspectorPanel/RoomInspector.tsx`: room details + editable fields.
- `InspectorPanel/WallInspector.tsx`: wall details display.
- `InspectorPanel/ProvenanceView.tsx`: deep-mode provenance breakdown.

#### Quantity

- `QuantityPanel/QuantityPanel.tsx`: quantity summary shell.
- `QuantityPanel/AreaSummaryTable.tsx`: per-room totals table.
- `QuantityPanel/ZoneBreakdown.tsx`: zone breakdown placeholder (stub text).
- `QuantityPanel/WallLengthSummary.tsx`: wall metric placeholder (stub tagged).

#### Layer and diagnostics

- `LayerPanel/LayerPanel.tsx`: layer visibility toggles.
- `DiagnosticsPanel/DiagnosticsPanel.tsx`: diagnostics container.
- `DiagnosticsPanel/DecisionLogView.tsx`: decision log placeholder (stub text).
- `ScalePanel/ScalePanel.tsx`: detected scale and override display.

### Toolbar (`frontend/src/toolbar`)

- `Toolbar.tsx`: top toolbar composition.
- `ModeSwitcher.tsx`: select/edit/split/merge mode control.
- `UndoRedo.tsx`: undo/redo controls.
- `ExportButton.tsx`: export action trigger.
- `ConfidenceFilter.tsx`: confidence-tier filtering control.

### Client state stores (`frontend/src/state`)

- `jobStore.ts`: current job status/result state.
- `canvasStore.ts`: viewport, active layers, and mode state.
- `selectionStore.ts`: selected room/wall IDs.
- `editStore.ts`: local undo/redo timeline.
- `quantityStore.ts`: derived quantity state.

### Hooks (`frontend/src/hooks`)

- `useJob.ts`: upload/progress/result lifecycle hook.
- `useCanvasInteraction.ts`: canvas controller hookup (stub note present).
- `useRoomEdit.ts`: polygon/label/split/merge edit actions.
- `useQuantities.ts`: reactive quantity recomputation.

### Shared UI (`frontend/src/shared`)

- `LoadingSpinner.tsx`: loading affordance.
- `Tooltip.tsx`: reusable tooltip wrapper.
- `ConfidenceBadge.tsx`: tier badge visual.

## Test grounding map

### Backend tests (`tests`)

- `tests/unit/test_config.py`: config parsing expectations.
- `tests/unit/test_adapters/test_registry.py`: adapter registration invariants.
- `tests/unit/test_fusion/test_trust.py`: trust weight logic behavior.
- `tests/unit/test_geometry/test_topology_stub.py`: topology module skeleton tests.
- `tests/integration/test_light_pipeline.py`: light path integration checks.
- `tests/integration/test_deep_pipeline.py`: deep path integration checks.

### Frontend tests (`frontend/tests`)

- `frontend/tests/canvas/coordinate_transform.test.ts`: transform math verification.
- `frontend/tests/integration/smoke.test.ts`: baseline integration smoke.

## Known skeleton reality vs target architecture

The file layout is mostly aligned to the technical brief, but implementation depth is intentionally incomplete:

- most backend stage modules still raise `NotImplementedError`
- multiple frontend layers/panels still explicitly mark themselves as stubs
- `vendors/` is present but empty
- worker path is scaffolded but not fully productionized

This means future work should prioritize filling implementation in existing files, not inventing parallel structures.

## Implementation routing by feature request

Use this section to decide where to code before touching files.

- Upload + job orchestration: `backend/api/routes/upload.py`, `backend/services/job_service.py`, `frontend/src/pages/UploadPage/*`, `frontend/src/hooks/useJob.ts`
- Pipeline runtime progression: `backend/pipeline/pipeline.py`, stage files under `backend/pipeline/stage*/`, worker `task_runner.py`
- Scale extraction/override: `backend/pipeline/stage1_5_scale/*`, `backend/api/routes/scale.py`, `frontend/src/panels/ScalePanel/ScalePanel.tsx`
- Fusion behavior: `backend/pipeline/stage2_fusion/*`, `tests/unit/test_fusion/test_trust.py`
- Geometry edits and validation: `backend/services/edit_service.py`, `backend/pipeline/stage3_geometry/*`, `frontend/src/hooks/useRoomEdit.ts`, `frontend/src/canvas/interactions/*`
- Canvas rendering and overlays: `frontend/src/canvas/*`, `frontend/src/panels/LayerPanel/LayerPanel.tsx`
- Diagnostics and transparency: `backend/api/routes/diagnostics.py`, `backend/pipeline/stage2_fusion/deep/diagnostics.py`, `frontend/src/panels/DiagnosticsPanel/*`, `frontend/src/canvas/layers/ConfidenceHeatmap.tsx`, `ContestedZoneLayer.tsx`
- Quantity and exports: `backend/services/quantity_service.py`, `backend/services/export_service.py`, `backend/api/routes/export.py`, `frontend/src/panels/QuantityPanel/*`, `frontend/src/toolbar/ExportButton.tsx`

## Guardrails for all coding agents

- Keep API shapes compatible with `frontend/src/api/types.ts` and backend schemas.
- Prefer deterministic, config-driven logic for Phase 1 fusion.
- Preserve user-overridable edits; never block on topology warnings.
- Keep deep diagnostics optional and toggle-driven in the viewer.
- Preserve confidence tier semantics (`high`, `needs_review`, `low_confidence`) and thresholds from the briefs.

