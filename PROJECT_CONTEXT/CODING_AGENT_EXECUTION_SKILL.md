---
name: civil-agent-execution-flexible
description: Actionable workflow for implementing Civil Agent features with a structure-first mindset that is flexible. Use when coding backend pipeline stages, API routes, frontend canvas/panels, tests, and exports, including justified refactors that expand or contract project structure.
---

# Civil Agent Flexible Execution Skill

## Mission

Implement Phase 1 features with bias toward existing files first, while allowing justified structural evolution when needed.

## Source-of-truth documents

Read these before coding:

1. `PROJECT_CONTEXT/PRODUCT_BRIEF.md`
2. `PROJECT_CONTEXT/TECHNICAL_BRIEF.md`
3. `PROJECT_CONTEXT/CODEBASE_PIPELINE_GROUNDING.md`

## Constraints and flexibility rules

- Prefer existing paths first before creating or removing structure.
- Add folders/files when they improve separation of concerns, readability, testing, or feature delivery.
- Remove/consolidate structure when it reduces duplication and preserves required behavior.
- Keep architecture consistent with current stage folders and route modules.
- Preserve Phase 1 scope boundaries.
- Prefer deterministic, config-driven behavior over hardcoded values.

## Execution protocol for every task

1. **Locate responsibility first**
   - Map requested behavior to exact existing files via `CODEBASE_PIPELINE_GROUNDING.md`.
   - If no mapping exists or mapping is weak, define the minimal structural change that cleanly fits the briefs, then implement it.

2. **Touch minimum viable surface**
   - Modify only the files necessary for the requested behavior.
   - Keep data contracts aligned between backend schemas and frontend API types.

3. **Implement in pipeline order**
   - For backend logic, preserve stage sequence:
     - stage0 -> stage1 -> stage1_5 -> stage2 -> stage3 -> stage4
   - For UI logic, preserve viewer workflow:
     - fetch -> render layers -> inspect -> edit -> recompute -> export

4. **Close the loop with tests**
   - Backend: update or add assertions in `tests/unit/*` and `tests/integration/*` if behavior changed.
   - Frontend: update tests under `frontend/tests/*` for affected interaction logic.

5. **Validate guardrails**
   - No out-of-scope features.
   - No breaking API field renames unless requested.
   - Confidence tiers and scale behavior remain consistent with briefs.

## File targeting playbook

### Upload and job lifecycle

- Backend: `backend/api/routes/upload.py`, `backend/api/routes/jobs.py`, `backend/services/job_service.py`, `backend/storage/job_store.py`
- Frontend: `frontend/src/pages/UploadPage/*`, `frontend/src/hooks/useJob.ts`, `frontend/src/state/jobStore.ts`

### Pipeline runtime and orchestration

- `backend/pipeline/pipeline.py`
- `backend/worker/task_runner.py`
- `backend/pipeline/core/{config.py,schemas.py,registry.py}`

### Perception and model adapters

- `backend/pipeline/stage1_perception/perception_orchestrator.py`
- `backend/pipeline/stage1_perception/density_map_synthesizer.py`
- `backend/pipeline/stage1_perception/adapters/*.py`

### Scale extraction and override

- `backend/pipeline/stage1_5_scale/*.py`
- `backend/api/routes/scale.py`
- `frontend/src/panels/ScalePanel/ScalePanel.tsx`

### Fusion

- Light: `backend/pipeline/stage2_fusion/light/light_fusion.py`
- Deep: `backend/pipeline/stage2_fusion/deep/{agreement.py,boundary_fusion.py,room_fusion.py,reconciliation.py,diagnostics.py}`
- Shared: `backend/pipeline/stage2_fusion/{trust.py,fusion_router.py}`

### Geometry and topology

- `backend/pipeline/stage3_geometry/{region_extractor.py,topology.py,split_merge.py,boundary_snap.py}`
- Edit entry: `backend/services/edit_service.py`

### Output and export

- Pipeline output: `backend/pipeline/stage4_output/{room_object.py,metadata.py,serializer.py}`
- API export path: `backend/api/routes/export.py`, `backend/services/export_service.py`
- Frontend trigger: `frontend/src/toolbar/ExportButton.tsx`

### Viewer and editing UX

- Canvas root/layers: `frontend/src/canvas/*`
- Panels: `frontend/src/panels/*`
- Toolbar: `frontend/src/toolbar/*`
- Hooks/stores: `frontend/src/hooks/*`, `frontend/src/state/*`

## Feature-to-file quick routing

- "Fix confidence colors": `frontend/src/canvas/utils/color_scales.ts`, `frontend/src/shared/ConfidenceBadge.tsx`, `frontend/src/toolbar/ConfidenceFilter.tsx`
- "Scale warning behavior": `backend/pipeline/stage1_5_scale/*`, `frontend/src/panels/ScalePanel/ScalePanel.tsx`, `frontend/src/panels/QuantityPanel/*`
- "Split/merge bug": `frontend/src/canvas/interactions/{SplitController.ts,MergeController.ts}`, `frontend/src/hooks/useRoomEdit.ts`, `backend/api/routes/edit.py`, `backend/services/edit_service.py`, `backend/pipeline/stage3_geometry/split_merge.py`
- "Diagnostics display mismatch": `backend/pipeline/stage2_fusion/deep/diagnostics.py`, `backend/api/routes/diagnostics.py`, `frontend/src/panels/DiagnosticsPanel/*`, `frontend/src/canvas/layers/{ConfidenceHeatmap.tsx,ContestedZoneLayer.tsx}`
- "Export format issue": `backend/services/export_service.py`, `backend/api/routes/export.py`, optionally `backend/pipeline/stage4_output/serializer.py`

## Implementation quality checks

Before finishing any task:

- Ensure changed code is either in mapped files or in intentionally added paths with clear purpose.
- Confirm any new/removed directories are intentional and documented in the change summary.
- Confirm route payloads still match `frontend/src/api/types.ts`.
- Verify scale-none behavior still yields pixel-unit-safe handling.
- Verify confidence tier naming is unchanged: `high`, `needs_review`, `low_confidence`.
- Validate touched tests, or document exactly what remains to validate.

## Anti-patterns to avoid

- Adding parallel "v2" folders instead of filling current modules.
- Restructuring the tree without a concrete engineering reason.
- Replacing deterministic fusion with learned fusion (out of Phase 1 scope).
- Blocking user edits on topology violations (must warn, not hard-fail).
- Hardcoding model input sizes globally instead of handling per adapter.
- Introducing frontend features outside upload-processing-viewer-edit-export flow.

## Done criteria for a coding task

A task is done only when:

1. behavior is implemented in the proper existing files
2. contracts remain consistent across backend and frontend
3. obvious regressions are checked via tests or targeted verification
4. structural changes (if any) are justified, minimal, and Phase 1 aligned

