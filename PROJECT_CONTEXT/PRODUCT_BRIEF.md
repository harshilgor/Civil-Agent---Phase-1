# Civil Agent — Product Brief for Implementation

> **Purpose of this document:** This is the grounding context for an AI coding agent building Civil Agent. Every implementation decision should trace back to something in this brief. If a feature isn't here, don't build it. If a behavior is described here, it's required.

---

## What You Are Building

Civil Agent is a web application that takes a floor plan image (PNG, JPG, or rasterized PDF), runs it through an AI pipeline, and produces an interactive workspace where users can view, inspect, edit, and export structured room and wall data extracted from that drawing.

The users are engineers, contractors, and construction teams. They are not ML engineers. They do not care about model names, logits, or agreement maps. They care about: are the rooms detected correctly, are the measurements right, and can I fix it if they're wrong.

---

## Core Product Principles

These four rules govern every UI/UX decision:

1. **Interactive, not static.** The output is not an image or a PDF. It is a live, manipulable canvas where every detected room and wall is a clickable, editable object.
2. **Reviewable, not black-box.** The user can always see WHY the system made a decision — confidence scores, warnings, and in Deep mode, which models agreed or disagreed.
3. **Assist decision-making, not replace it.** The system proposes; the user disposes. Every AI output is a suggestion that can be overridden.
4. **Editable and auditable.** Every result can be corrected by the user, and every correction is tracked. The system never locks the user out of fixing something.

---

## User Flow

The complete user journey has five phases:

### Phase 1: Upload
- User opens the application and sees an upload interface.
- They drag-and-drop or file-pick a floor plan image (PNG, JPG) or PDF.
- They choose a processing mode: **Light** (fast, everyday use) or **Deep** (slower, higher accuracy, more diagnostics).
- Optionally, they can provide a known scale (e.g., "1:100" or "1 inch = 4 feet"). If they don't, the system will attempt to detect it.
- They click "Analyze" to submit.

### Phase 2: Processing
- The system shows a progress indicator while the pipeline runs.
- Progress is stage-by-stage: "Normalizing input…" → "Detecting rooms and walls…" → "Fusing results…" → "Validating geometry…" → "Done."
- In an ideal implementation, partial results stream in as stages complete (e.g., detected boundaries appear on the canvas before room labeling is done).
- The user waits. Light mode should target under 30 seconds. Deep mode may take 1–3 minutes.

### Phase 3: Viewing
- The main workspace opens. It is composed of:
  - **A canvas** (center): shows the original floor plan image with detected room polygons and wall segments overlaid as colored, interactive vector shapes.
  - **An inspector panel** (right sidebar): shows properties of the currently selected object.
  - **A quantity panel** (bottom bar or collapsible): shows summary metrics — total floor area, room-by-room table, wall lengths.
  - **A toolbar** (top): mode switches (Select / Edit / Split / Merge), undo/redo, export, confidence filter.
  - **A layer panel** (left sidebar or toggle): controls which overlays are visible — original image, room polygons, boundaries, confidence heatmap, contested zones.

### Phase 4: Reviewing & Editing
- The user clicks a room polygon to select it. The inspector shows: room label, area, perimeter, confidence score, confidence tier (High / Needs Review / Low), and any warnings.
- In **Deep mode**, the inspector additionally shows: which models contributed to this room, agreement score, decision path (e.g., "Accepted after boundary-enforced split in Pass A, composite score 0.74").
- The user can:
  - **Relabel** a room by selecting a different room type from a dropdown.
  - **Adjust boundaries** by dragging polygon vertices.
  - **Split** a room by drawing a dividing line across it.
  - **Merge** two adjacent rooms by selecting both and clicking merge.
  - **Override scale** by entering a known dimension.
- Every edit triggers server-side recomputation of areas, perimeters, and topology validation. The quantity panel updates live.
- Undo/redo is available for all edits.

### Phase 5: Export
- The user exports results in one or more formats:
  - **JSON** — structured room objects with polygons, labels, areas, confidence.
  - **GeoJSON** — for GIS integration.
  - **CSV** — quantity takeoff table (room label, area, perimeter).
- Exports reflect all user edits applied on top of AI outputs.

---

## Product Layers (What the System Must Display)

These six layers map directly to UI features. Each one must be implemented.

### Layer 1: Drawing Understanding
**What the user sees:** Their uploaded floor plan with colored overlays showing detected rooms and walls.
**Implementation requirement:** The canvas renders the original image as a base raster layer, with room polygons and boundary segments as vector layers on top.

### Layer 2: Object-Based View
**What the user sees:** Rooms as individual clickable shapes, walls as measurable line segments. Not a heatmap, not a segmentation mask — discrete objects.
**Implementation requirement:** Each room and wall must have a unique ID, be independently selectable, and show its properties in the inspector.

### Layer 3: Quantity Insights
**What the user sees:** A summary panel showing room areas (in m² or ft²), wall lengths, total floor area, and zone-based breakdowns (e.g., "Wet zones: 23m², Living areas: 45m²").
**Implementation requirement:** All quantities must be computed from the polygon geometry and the scale factor. If no scale was detected, show pixel-unit quantities with a clear warning: "Scale not detected — quantities are in pixels, not real units."

### Layer 4: Review & Correction
**What the user sees:** Edit tools — vertex dragging, room splitting, room merging, relabeling, scale override.
**Implementation requirement:** Edits are applied to the stored result set. The backend revalidates topology after every edit (no overlapping rooms, no leaking boundaries). Undo/redo stack is mandatory.

### Layer 5: Confidence & Transparency
**What the user sees:** Color-coded rooms (green = high confidence, yellow = needs review, red = low confidence). Warnings on uncertain regions. In Deep mode: agreement heatmap overlay, contested zone highlights.
**Implementation requirement:**
- Every room object has a `composite_score` (0.0–1.0) and a `confidence_tier` ("high" / "needs_review" / "low_confidence").
- Confidence thresholds: ≥ 0.70 = high, 0.50–0.70 = needs_review, < 0.50 = low_confidence.
- The user can toggle a confidence filter to show only rooms that need review.
- In Deep mode, the user can toggle an agreement heatmap overlay (per-pixel, 0.0–1.0) and see highlighted contested zones where models disagreed on topology.

### Layer 6: Structural Intelligence (Phase 1 Scope — Minimal)
**What the user sees:** In Phase 1, this is limited. The system may highlight potential structural support zones based on wall thickness and room layout patterns, but it does NOT generate structural recommendations.
**Implementation requirement for Phase 1:** Surface any structural constraint flags that emerge from the pipeline (e.g., "This wall appears to be load-bearing based on thickness"). Do not build a structural analysis engine — this is future scope.

---

## Processing Modes

### Light Mode
- **Models used:** 1 per task (CubiCasa for rooms, DeepFloorplan for boundaries).
- **Fusion:** Deterministic — threshold boundaries, extract rooms, check consistency.
- **Speed target:** < 30 seconds.
- **Diagnostics available:** Per-region boundary support scores, basic consistency flags.
- **Best for:** Quick takeoffs, everyday use, simple floor plans.

### Deep Mode
- **Models used:** 2–3 per task (CubiCasa + DeepFloorplan + RoomFormer/PolyRoom for rooms; CubiCasa + DeepFloorplan + Raster-to-Graph for boundaries).
- **Fusion:** 5 sub-stage hierarchical ensemble with trust hierarchy, agreement maps, cross-task reconciliation.
- **Speed target:** 1–3 minutes.
- **Diagnostics available:** Full agreement maps, per-model outputs preserved, contested zone list, decision log per region, rejected region list.
- **Best for:** Complex floor plans, high-stakes decisions, detailed review workflows.

The user selects the mode before upload. They cannot switch modes after processing without re-running the pipeline.

---

## Room Types (Label Set)

The following room types should be available as labels in the UI dropdown for relabeling. This set comes from the CubiCasa5K dataset's class schema:

Background, Outdoor, Wall, Kitchen, Living Room, Bedroom, Bathroom, Entry, Railing, Storage, Garage, Undefined.

Additionally, icons detected (from CubiCasa) include: Window, Door, Closet, Electrical Appliance, Toilet, Sink, Sauna Bench, Fire Place, Bathtub, Chimney. These are not rooms but may be surfaced as additional detail in a future version.

---

## Scale Handling

Scale is critical. Without it, areas and lengths are meaningless.

**Detection priority (fallback hierarchy):**
1. Detected scale bar in the drawing → highest confidence.
2. Dimension annotations with consistent cross-checks → high confidence.
3. Title block text (e.g., "1:100") → moderate confidence.
4. User-provided scale → accepted as override at any time.
5. No scale found → output is flagged as "topology only, no metric quantities."

**UI requirements:**
- The Scale Panel always shows: detected scale factor, confidence level (high/moderate/low/none), and source method.
- If scale confidence is "none," all quantity displays must show a prominent warning.
- The user can override scale at any time. Overriding sets confidence to "user_override" and recomputes all quantities.

---

## Error States the UI Must Handle

1. **Upload failure:** Invalid file format, file too large, corrupted image → show error message, allow retry.
2. **Pipeline failure:** Model crashes, GPU OOM, timeout → show error with stage name where failure occurred, allow retry.
3. **No rooms detected:** Pipeline completes but finds 0 rooms → show the original image with a message: "No rooms could be detected in this drawing. The image may not contain a recognizable floor plan."
4. **Low overall confidence:** All detected rooms score below 0.50 → show results but with a banner: "Results have low confidence. Manual review is strongly recommended."
5. **Scale not detected:** All metric quantities show in pixels with a warning badge.

---

## What Is NOT in Phase 1

The following are explicitly out of scope for Phase 1. Do not build them:

- Multi-page PDF support (only first page is rasterized).
- Multi-floor analysis.
- 3D model generation.
- Structural analysis engine (beyond surfacing basic flags).
- Learned fusion (Phase 1 uses rule-based fusion only).
- User accounts, authentication, project management.
- Collaboration features.
- Version history of edits (undo/redo is in scope; persistent history is not).
- Cost estimation.
- Integration with BIM software.
- Mobile-optimized UI (desktop-first).

---

## File Formats

**Input:** PNG, JPG, PDF (first page rasterized at ≥150 DPI).

**Output (export):**
- JSON: Array of room objects, each with `{id, label, polygon: [[x,y]...], area_m2, area_px, perimeter_m2, perimeter_px, confidence_score, confidence_tier, flags}`.
- GeoJSON: Standard FeatureCollection with room polygons as Features.
- CSV: Tabular format — one row per room: `id, label, area_m2, perimeter_m2, confidence_tier`.

---

## Performance Expectations

- Upload → processing start: < 2 seconds.
- Light mode pipeline: < 30 seconds for a typical residential floor plan (single floor, < 15 rooms).
- Deep mode pipeline: < 3 minutes for the same.
- Canvas interaction (pan, zoom, select): 60fps with no perceptible lag.
- Edit → quantity recomputation: < 500ms.
- Export generation: < 2 seconds.

---

## Design Direction

The UI should feel like a professional tool, not a consumer app. Reference points: Figma (canvas interaction model), QGIS (layer management), Bluebeam Revu (construction document workflow). Clean, minimal chrome. The canvas is the star — maximize its screen real estate. Sidebars should be collapsible. The toolbar should be compact.

Color palette for confidence: use a traffic-light scheme — green (#22C55E) for high confidence, amber (#F59E0B) for needs_review, red (#EF4444) for low_confidence. Room fill colors should be semi-transparent so the underlying drawing is always visible.