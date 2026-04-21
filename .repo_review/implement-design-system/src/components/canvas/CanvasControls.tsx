"use client";

import { Minus, Plus, Maximize2 } from "lucide-react";
import type { LayerKey, OverlayMode } from "@/stores/canvasStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { LAYER_LABELS } from "./PlanCanvas2D";

type Props = {
  maxFloors: number;
  overlayModes?: OverlayMode[];
  allowFloorAll?: boolean;
  disableViewToggle?: boolean;
};

export function CanvasControls({
  maxFloors,
  overlayModes = ["none"],
  allowFloorAll = true,
  disableViewToggle,
}: Props) {
  const viewMode = useCanvasStore((s) => s.viewMode);
  const setViewMode = useCanvasStore((s) => s.setViewMode);
  const overlayMode = useCanvasStore((s) => s.overlayMode);
  const setOverlayMode = useCanvasStore((s) => s.setOverlayMode);
  const zoom = useCanvasStore((s) => s.zoom);
  const zoomIn = useCanvasStore((s) => s.zoomIn);
  const zoomOut = useCanvasStore((s) => s.zoomOut);
  const resetView = useCanvasStore((s) => s.resetView);
  const floor = useCanvasStore((s) => s.floor);
  const setFloor = useCanvasStore((s) => s.setFloor);
  const layers = useCanvasStore((s) => s.layers);
  const toggleLayer = useCanvasStore((s) => s.toggleLayer);

  return (
    <div className="absolute top-vs-3 left-vs-3 z-20 w-[220px] rounded-sm border-hairline bg-surface-container-lowest/95 backdrop-blur-sm shadow-elev-2 flex flex-col divide-hairline">
      <div className="px-vs-3 py-vs-2 flex items-center gap-vs-1">
        {!disableViewToggle && (
          <div className="flex-1 flex items-center">
            {(["2d", "3d"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setViewMode(m)}
                className={[
                  "flex-1 h-6 text-body-sm font-medium tonal-hover rounded-sm",
                  viewMode === m
                    ? "bg-on-surface text-on-primary"
                    : "text-on-surface-variant hover:bg-surface-container-low",
                ].join(" ")}
              >
                {m.toUpperCase()}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="px-vs-3 py-vs-2 flex items-center gap-vs-2">
        <button
          type="button"
          onClick={zoomOut}
          className="w-7 h-7 rounded-sm hover:bg-surface-container-low inline-flex items-center justify-center"
          aria-label="Zoom out"
        >
          <Minus className="w-3 h-3" />
        </button>
        <div className="flex-1 font-mono text-[11px] text-center text-on-surface-variant">
          Zoom {Math.round(zoom * 100)}%
        </div>
        <button
          type="button"
          onClick={zoomIn}
          className="w-7 h-7 rounded-sm hover:bg-surface-container-low inline-flex items-center justify-center"
          aria-label="Zoom in"
        >
          <Plus className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={resetView}
          className="w-7 h-7 rounded-sm hover:bg-surface-container-low inline-flex items-center justify-center"
          aria-label="Fit view"
          title="Fit view (F)"
        >
          <Maximize2 className="w-3 h-3" />
        </button>
      </div>
      <div className="px-vs-3 py-vs-2 flex items-center gap-vs-2">
        <span className="text-body-sm text-on-surface-variant">Floor</span>
        <select
          value={floor === "all" ? "all" : String(floor)}
          onChange={(e) =>
            setFloor(e.target.value === "all" ? "all" : parseInt(e.target.value, 10))
          }
          className="flex-1 h-7 px-vs-2 border-hairline rounded-sm bg-surface text-body-sm outline-none focus:border-secondary"
        >
          {allowFloorAll && <option value="all">All</option>}
          {Array.from({ length: maxFloors }, (_, i) => i + 1).map((f) => (
            <option key={f} value={f}>
              Floor {f}
            </option>
          ))}
        </select>
      </div>
      {overlayModes.length > 1 && (
        <div className="px-vs-3 py-vs-2 flex flex-col gap-vs-1">
          <span className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
            Overlay
          </span>
          <div className="flex flex-wrap gap-vs-1">
            {overlayModes.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setOverlayMode(m)}
                className={[
                  "h-6 px-vs-2 rounded-sm text-body-sm font-medium tonal-hover",
                  overlayMode === m
                    ? "bg-on-surface text-on-primary"
                    : "bg-surface text-on-surface-variant hover:bg-surface-container-low",
                ].join(" ")}
              >
                {overlayLabel(m)}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="px-vs-3 py-vs-2 flex flex-col gap-vs-1">
        <span className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          Layers
        </span>
        {(Object.keys(layers) as LayerKey[]).map((k) => (
          <label
            key={k}
            className="flex items-center gap-vs-2 cursor-pointer text-body-sm"
          >
            <input
              type="checkbox"
              className="accent-[var(--secondary)]"
              checked={layers[k]}
              onChange={() => toggleLayer(k)}
            />
            <span>{LAYER_LABELS[k]}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function overlayLabel(m: OverlayMode): string {
  switch (m) {
    case "none":
      return "None";
    case "zones":
      return "Zones";
    case "supports":
      return "Supports";
    case "load_paths":
      return "Loads";
    case "utilization":
      return "Utilization";
  }
}
