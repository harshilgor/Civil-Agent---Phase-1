# Vellum Structures Design System

**Creative North Star — "The Digital Vellum"**
A warm, tactile, engineer's-drafting-table aesthetic for structural-design software. Paper-stock surfaces, technical charcoal type, and functional color used as *data* (not decoration). No opaque borders, no generic shadows, strict 4/8 baseline grid.

## Product context

This system is built around **Vellum Structures** — a family of screens for structural engineers who analyze buildings represented as graphs (walls, cores, columns, zones, support spans). The primary surface is a canvas of drafting-paper with overlaid structural drawings, flanked by two information sidebars (navigation left, project specs right).

### Sources explored
- **Codebase (read-only):** `stitch_structural_design_graph_viewer/` — 9 reference HTML screens + `vellum_draft/DESIGN.md`:
  - `3d_interactive_working_view/` — 3D isometric viewport + terminal command bar
  - `building_graph_viewer/` — plan-view floor plan with layer toggles
  - `dashboard_project_list/` — project table with bento stats
  - `design_summary_export/` — summary report UI
  - `file_upload_processing/` — drop-zone & ingestion progress
  - `project_dashboard_v2_portfolio_view/` — alternate dashboard layout
  - `project_input_form/` — structured input form
  - `structural_zones_overlay/` — zone overlay selector
  - `support_span_map/` — span-map visualization
- **DESIGN.md** — the governing creative direction ("The Digital Vellum")

## Products represented

A single web application, **Vellum Structures** (referenced in code as `VELLUM_STRUCTURES` and, in sample content, as *Helix Tower v2.4*). It is not a multi-product suite — all nine screens are views within the same engineering tool.

## Iconography

**Material Symbols Outlined** (Google Fonts icon font) is the single icon system used everywhere in the codebase. Weight 300 at 24px, fill 0 by default; fill 1 is used only for status indicators (`check_circle`, `warning`). No emoji. No hand-drawn SVGs beyond data-visualization primitives (circles for columns, lines for walls, rects for zones).

Usage: `<span class="material-symbols-outlined">settings</span>`

Because the set is CDN-delivered and identical in both the source and this system, no substitution or copying is needed — it is referenced directly from Google Fonts in `colors_and_type.css`.

## Content fundamentals

**Voice.** Quiet, declarative, technical. The UI talks *about* the model, not to the user. Sentences are short and factual: "Span at Grid C-4 exceeds 12m limit." "Foundation capacity assumes Class C soil profile." Never "we", never "you". No exclamation marks. No marketing copy.

**Casing.**
- Section labels and metadata: `UPPERCASE` with wide tracking (0.14em) — mimics blueprint title-block notation.
- Screen titles: Title Case, Space Grotesk, tight tracking.
- Button text: Title Case (`New Project`, `Export`) — *not* all-caps for primary buttons in buttons > 40px tall; smaller terminal-style buttons may use `UPPER_CASE_WITH_UNDERSCORES` (e.g. `NEW_CALCULATION`, `TERMINAL_READY`).
- Body: sentence case.

**Numbers and units.** Always precise. "84.2%", "3,850 m²", "0.992", "450 kN/m". Units sit in `label-sm` next to the value (the "Big & Small" pairing). Decimals are preserved even when they could be rounded — precision is the brand.

**Terminology.** Engineering-specific and unapologetically jargon-heavy: *confidence interval*, *load path*, *transfer beam*, *grid alignment*, *zone compatibility*, *span*, *core*, *void*, *pedestrian corridor*. The UI assumes a literate audience.

**Emoji.** Never. Not in content, not in labels, not in empty states.

**Examples from the product:**
- Status: *Verified (L1–L4)* · *Needs Review* · *Processing* · *Complete*
- Warning: *"Span at Grid C-4 exceeds 12m limit. Transfer beam required or additional support candidate."*
- Assumption: *"All internal partitions are non-load bearing unless tagged."*
- Annotation: *ZONE_ALPHA_TEAL* · *FLOW_CORRIDOR_PINK* · *VOID_PLATE_PURPLE*
- Terminal: *Terminal_Prompt > Move column B-3 to position 8500, 12000*

## Visual foundations

**Color.** Warm paper `#fbf9f2` is the only real background; every "container" is a tonal step (`surface-container-low` → `surface-container-highest`). Foreground is charcoal `#313429`, never `#000`. Functional accents (teal, purple, pink, coral, blue, red/amber/green) are reserved for *data* — a teal chip means "verified structural spine", not "this is a secondary action". Full palette: `colors_and_type.css`.

**Type.** Dual-family: **Space Grotesk** for headlines and metric values (geometric, technical-brutalist), **Inter** for body and labels (workhorse). Labels are small (11px), uppercase, and carry 0.14em letter-spacing so they read as blueprint annotations. Monospace (JetBrains Mono) appears only in terminal surfaces and coordinate values.

**Spacing & grid.** Strict 4px / 8px baseline. Generous and unequal margins — sidebars pin to the edges, main content floats with asymmetric whitespace. Swiss-modular in rhythm but never perfectly symmetric.

**Backgrounds.** The signature is a drafting-paper canvas: `#fbf9f2` base + a 40px orthogonal grid at 5% charcoal. No full-bleed photography. No illustrations beyond technical floor plans and isometric extrusions rendered as SVG. A subtle "grain" overlay (3% opacity noise texture) appears on hero surfaces.

**Animation.** Restrained. `cubic-bezier(0.2, 0, 0, 1)` at 120–320ms. Fades and small position shifts (`active:scale-95` presses, translate-x-1 on chevrons). Zero bounces, zero spring physics. `animate-pulse` on live-status indicators only. Long operations show `animate-spin` on the refresh icon.

**Hover states.** Background flips to `surface-container-low` or `surface-container-high` (tonal, never a color change). Icons and secondary text move from `opacity: 0.6` → `1`. No glows.

**Press states.** `transform: scale(0.95)` for buttons; immediate background tone drop. No color flash.

**Borders.** The "No-Line" rule. 1px opaque borders are prohibited. When a line is needed it is `0.5px solid rgba(49, 52, 41, 0.10)` (`--hairline`). Separation prefers tonal shifts and whitespace over strokes. A single bold line is permitted at the start of an error block (`border-l-2 border-error`).

**Shadows.** Avoid software-generic shadows. When an element must float, use blur 24–32px at 4% charcoal opacity (`--elev-2` / `--elev-3`). Never a drop shadow darker than 6%.

**Glassmorphism.** Reserved for floating overlays above the canvas (layer toggles, HUD info panels): `bg-surface/80` + `backdrop-blur(20px)`. This lets the drawing bleed through.

**Corner radii.** `none`, `sm` (2px), or `md` (4px) for structural UI. `lg` (8px) only on floating overlay pills. `xl` / `full` are banned on engineering components.

**Cards.** No rounded corners beyond 2px. No drop shadow by default. Tonal-step the background only (`surface-container-low` against `surface`). Optionally a single 2px accent border on one edge to mark a critical card.

**Imagery mood.** Warm, low-contrast, paper-toned. When reference imagery appears (e.g. active model thumbnail), it is blended `mix-blend-multiply` at 60% opacity onto a warm container — never full-color photographs.

**Transparency & blur.** Only on floating overlays and the terminal input. The rest of the UI is opaque.

**Fixed elements.** Top app bar (64px or 48px on the 3D view), left nav (256–280px), right specs panel (320px), bottom terminal bar (40px, dark). Main canvas floats between them.

## Tokens summary

- **Surface stack:** `surface` → `surface-container-low` → `surface-container` → `surface-container-high` → `surface-container-highest`
- **Foundation ink:** `on-surface` `#313429`, `on-surface-variant` `#5e6054`, `primary` `#5f5e5e`
- **Accents:** `secondary` (teal `#006a6a`), `fn-purple`, `fn-pink`, `fn-coral`, `fn-blue`
- **Safety:** `success`, `warning`, `error` `#9f403d`
- **Lines:** `outline` `#7a7c6f`, `outline-variant` `#b2b3a5` — ALWAYS used with alpha
- **Radii:** none / sm (2px) / md (4px) — cap at 8px for overlays

## Index

| File | Purpose |
|---|---|
| `colors_and_type.css` | All CSS variables: color, type, spacing, elevation |
| `README.md` | This file — context, content & visual foundations |
| `SKILL.md` | Agent-Skill descriptor (cross-compatible with Claude Code) |
| `preview/` | Small HTML specimen cards (registered as assets) |
| `ui_kits/vellum_structures/` | Interactive click-through recreation of the app |
| `assets/` | Logos, icon references, background patterns |

## Font notes

Both **Space Grotesk** and **Inter** are used directly from Google Fonts via `@import` in `colors_and_type.css`. No local font files are bundled — if offline use is required, download the WOFF2 files from fonts.google.com and self-host.

## Caveats

- **No real logos exist** in the source codebase. The wordmark `VELLUM_STRUCTURES` is a typographic treatment only — rendered in Space Grotesk 700, tight tracking. See `assets/wordmark.html`.
- **Material Symbols Outlined** is loaded from CDN. If offline use is needed, swap for self-hosted Material Symbols WOFF2.
- Functional colors (purple, pink, coral, blue) were *named* in DESIGN.md but not given hex values; I picked warm, desaturated values that sit harmoniously alongside the existing teal + charcoal. Flagged for review.
