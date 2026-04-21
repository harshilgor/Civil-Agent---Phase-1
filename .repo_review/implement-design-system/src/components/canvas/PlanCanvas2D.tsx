"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { BuildingGraph, StructuralGraph, StructuralZone, SupportClass, Wall } from "@/types/domain";
import { SUPPORT_COLOR, ZONE_FILL } from "@/lib/colors";
import { useCanvasStore, type LayerKey, type OverlayMode } from "@/stores/canvasStore";
import { useSelectionStore, type ElementKind } from "@/stores/selectionStore";

type Props = {
  graph: BuildingGraph;
  structural?: StructuralGraph | null;
  overlayMode?: OverlayMode;
  supportFilter?: Record<SupportClass, boolean>;
  onCursor?: (pt: { x: number; y: number } | null) => void;
};

/**
 * 2D Plan canvas — SVG renderer for the Building Graph.
 * Handles walls, grid, rooms, columns, cores, openings, and overlay modes.
 *
 * Implementation note: SVG was chosen over <canvas> because we need per-element
 * hit-testing + focus styles; with a few hundred elements SVG is plenty fast.
 */
export function PlanCanvas2D({ graph, structural, overlayMode = "none", supportFilter, onCursor }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const layers = useCanvasStore((s) => s.layers);
  const zoom = useCanvasStore((s) => s.zoom);
  const panX = useCanvasStore((s) => s.panX);
  const panY = useCanvasStore((s) => s.panY);
  const setZoom = useCanvasStore((s) => s.setZoom);
  const setPan = useCanvasStore((s) => s.setPan);
  const floor = useCanvasStore((s) => s.floor);
  const select = useSelectionStore((s) => s.select);
  const clear = useSelectionStore((s) => s.clear);
  const selection = useSelectionStore((s) => s.selection);
  const hover = useSelectionStore((s) => s.hover);
  const setHover = useSelectionStore((s) => s.setHover);

  const marginMm = 3000;
  const innerW = graph.lengthMm + marginMm * 2;
  const innerH = graph.widthMm + marginMm * 2;

  const viewBox = useMemo(() => {
    // Apply zoom + pan. Zoom < 1 = zoomed out (bigger vb), > 1 = zoomed in
    const w = innerW / zoom;
    const h = innerH / zoom;
    const cx = innerW / 2 + panX;
    const cy = innerH / 2 + panY;
    return `${cx - w / 2} ${cy - h / 2} ${w} ${h}`;
  }, [innerW, innerH, zoom, panX, panY]);

  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);

  function toModelCoords(ev: React.MouseEvent<SVGSVGElement>): [number, number] | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const p = pt.matrixTransform(ctm.inverse());
    return [p.x - marginMm, p.y - marginMm];
  }

  function handleMouseDown(ev: React.MouseEvent<SVGSVGElement>) {
    if (ev.button !== 0 && ev.button !== 1) return;
    // Only start panning if not clicking an element
    if ((ev.target as Element).closest("[data-el]")) return;
    setDragging(true);
    dragRef.current = { sx: ev.clientX, sy: ev.clientY, px: panX, py: panY };
  }

  function handleMouseMove(ev: React.MouseEvent<SVGSVGElement>) {
    const m = toModelCoords(ev);
    onCursor?.(m ? { x: m[0] / 1000, y: m[1] / 1000 } : null);
    if (!dragging || !dragRef.current) return;
    const dx = ev.clientX - dragRef.current.sx;
    const dy = ev.clientY - dragRef.current.sy;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const sx = (innerW / zoom) / rect.width;
    const sy = (innerH / zoom) / rect.height;
    setPan(dragRef.current.px - dx * sx, dragRef.current.py - dy * sy);
  }

  function handleMouseUp() {
    setDragging(false);
    dragRef.current = null;
  }

  useEffect(() => {
    // Wheel zoom
    const svg = svgRef.current;
    if (!svg) return;
    function onWheel(ev: WheelEvent) {
      if (ev.ctrlKey || ev.metaKey || ev.deltaY === 0) return;
      ev.preventDefault();
      const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
      setZoom(zoom * factor);
    }
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom, setZoom]);

  const currentFloor = floor === "all" ? null : floor;

  // Overlay preparation
  const zonesForFloor: StructuralZone[] =
    overlayMode === "zones" && structural
      ? structural.zones.filter((z) => currentFloor == null || z.floor === currentFloor)
      : [];

  const candidatesForFloor = useMemo(() => {
    if (!graph.columnCandidates) return [];
    if (currentFloor == null) {
      // dedupe by grid intersection (just use floor 1 representative)
      return graph.columnCandidates.filter((c) => c.floor === 1);
    }
    return graph.columnCandidates.filter((c) => c.floor === currentFloor);
  }, [graph.columnCandidates, currentFloor]);

  return (
    <svg
      ref={svgRef}
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-full select-none bg-canvas-grid"
      style={{ cursor: dragging ? "grabbing" : "grab" }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => {
        handleMouseUp();
        onCursor?.(null);
      }}
      onClick={(e) => {
        if ((e.target as Element).closest("[data-el]")) return;
        clear();
      }}
    >
      {/* Translate so that model (0,0) is at (marginMm, marginMm) */}
      <g transform={`translate(${marginMm} ${marginMm})`}>
        {/* Grid lines */}
        {layers.grid && <GridLayer graph={graph} />}

        {/* Zones overlay (below rooms/walls when in zones mode) */}
        {overlayMode === "zones" && (
          <ZonesLayer
            zones={zonesForFloor}
            selection={selection}
            hover={hover}
            onSelect={(id) => select("zone", id)}
            onHover={(id) => setHover("zone", id)}
          />
        )}

        {/* Rooms */}
        {layers.rooms && (
          <RoomsLayer
            graph={graph}
            selection={selection}
            hover={hover}
            onSelect={(id) => select("room", id)}
            onHover={(id) => setHover("room", id)}
          />
        )}

        {/* Cores */}
        {layers.cores && <CoresLayer graph={graph} />}

        {/* Walls */}
        {layers.walls && (
          <WallsLayer
            graph={graph}
            selection={selection}
            hover={hover}
            onSelect={(id) => select("wall", id)}
            onHover={(id) => setHover("wall", id)}
          />
        )}

        {/* Openings */}
        {layers.openings && <OpeningsLayer graph={graph} />}

        {/* Dimensions */}
        {layers.dimensions && (
          <DimensionsLayer graph={graph} structural={structural} />
        )}

        {/* Columns / support candidates */}
        {layers.columns && (
          <ColumnsLayer
            candidates={candidatesForFloor}
            overlayMode={overlayMode}
            supportFilter={supportFilter}
            selection={selection}
            hover={hover}
            onSelect={(id) => select("column", id)}
            onHover={(id) => setHover("column", id)}
          />
        )}
      </g>
    </svg>
  );
}

// ---- sub layers ----

function GridLayer({ graph }: { graph: BuildingGraph }) {
  const extend = 1500;
  const { grid, lengthMm, widthMm } = graph;
  return (
    <g>
      {grid.xAxes.map((a) => (
        <g key={`x${a.label}`}>
          <line
            x1={a.positionMm}
            x2={a.positionMm}
            y1={-extend}
            y2={widthMm + extend}
            stroke="rgba(49,52,41,0.4)"
            strokeWidth={10}
            strokeDasharray="120 90"
          />
          <GridBubble cx={a.positionMm} cy={-extend - 400} label={a.label} />
          <GridBubble cx={a.positionMm} cy={widthMm + extend + 400} label={a.label} />
        </g>
      ))}
      {grid.yAxes.map((a) => (
        <g key={`y${a.label}`}>
          <line
            y1={a.positionMm}
            y2={a.positionMm}
            x1={-extend}
            x2={lengthMm + extend}
            stroke="rgba(49,52,41,0.4)"
            strokeWidth={10}
            strokeDasharray="120 90"
          />
          <GridBubble cx={-extend - 400} cy={a.positionMm} label={a.label} />
          <GridBubble cx={lengthMm + extend + 400} cy={a.positionMm} label={a.label} />
        </g>
      ))}
    </g>
  );
}

function GridBubble({ cx, cy, label }: { cx: number; cy: number; label: string }) {
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={340}
        fill="var(--surface-container-lowest)"
        stroke="rgba(49,52,41,0.5)"
        strokeWidth={8}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="JetBrains Mono, monospace"
        fontSize={320}
        fill="var(--on-surface-variant)"
      >
        {label}
      </text>
    </g>
  );
}

function WallsLayer({
  graph,
  selection,
  hover,
  onSelect,
  onHover,
}: {
  graph: BuildingGraph;
  selection: { kind: ElementKind; id: string | null };
  hover: { kind: ElementKind; id: string | null };
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  return (
    <g>
      {graph.walls.map((w) => {
        const isSelected = selection.kind === "wall" && selection.id === w.id;
        const isHover = hover.kind === "wall" && hover.id === w.id;
        const stroke =
          w.type === "structural"
            ? "var(--on-surface)"
            : w.type === "shear"
              ? "var(--secondary)"
              : "rgba(49,52,41,0.45)";
        const thickness = Math.max(w.thicknessMm * 0.9, 80);
        return (
          <WallSegment
            key={w.id}
            w={w}
            stroke={stroke}
            thickness={thickness}
            selected={isSelected}
            hovered={isHover}
            onClick={() => onSelect(w.id)}
            onMouseEnter={() => onHover(w.id)}
            onMouseLeave={() => onHover(null)}
          />
        );
      })}
    </g>
  );
}

function WallSegment({
  w,
  stroke,
  thickness,
  selected,
  hovered,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: {
  w: Wall;
  stroke: string;
  thickness: number;
  selected: boolean;
  hovered: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  return (
    <g data-el="wall" onClick={onClick} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave} style={{ cursor: "pointer" }}>
      <line
        x1={w.start[0]}
        y1={w.start[1]}
        x2={w.end[0]}
        y2={w.end[1]}
        stroke={stroke}
        strokeWidth={thickness * (hovered ? 1.25 : 1)}
        strokeLinecap="square"
        opacity={selected ? 1 : hovered ? 0.95 : 0.9}
      />
      {selected && (
        <line
          x1={w.start[0]}
          y1={w.start[1]}
          x2={w.end[0]}
          y2={w.end[1]}
          stroke="var(--secondary)"
          strokeWidth={thickness + 120}
          strokeLinecap="square"
          opacity={0.35}
        />
      )}
    </g>
  );
}

function RoomsLayer({
  graph,
  selection,
  hover,
  onSelect,
  onHover,
}: {
  graph: BuildingGraph;
  selection: { kind: ElementKind; id: string | null };
  hover: { kind: ElementKind; id: string | null };
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  return (
    <g>
      {graph.rooms.map((r) => {
        const pts = r.polygon.map((p) => p.join(",")).join(" ");
        const isSel = selection.kind === "room" && selection.id === r.id;
        const isH = hover.kind === "room" && hover.id === r.id;
        const fill = ROOM_COLOR[r.type] ?? "rgba(49,52,41,0.05)";
        const cx = r.polygon.reduce((s, p) => s + p[0], 0) / r.polygon.length;
        const cy = r.polygon.reduce((s, p) => s + p[1], 0) / r.polygon.length;
        return (
          <g
            key={r.id}
            data-el="room"
            onClick={() => onSelect(r.id)}
            onMouseEnter={() => onHover(r.id)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: "pointer" }}
          >
            <polygon
              points={pts}
              fill={fill}
              fillOpacity={isSel ? 0.35 : isH ? 0.22 : 0.12}
              stroke={isSel ? "var(--secondary)" : "transparent"}
              strokeWidth={60}
            />
            <text
              x={cx}
              y={cy - 200}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={380}
              fill="var(--on-surface)"
              opacity={0.8}
              fontFamily="Inter, sans-serif"
              pointerEvents="none"
            >
              {r.label}
            </text>
            <text
              x={cx}
              y={cy + 300}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={260}
              fill="var(--on-surface-variant)"
              fontFamily="JetBrains Mono, monospace"
              pointerEvents="none"
            >
              {r.areaM2.toFixed(0)} m²
            </text>
          </g>
        );
      })}
    </g>
  );
}

const ROOM_COLOR: Partial<Record<string, string>> = {
  office: "#5DCAA5",
  open_plate: "#7F77DD",
  corridor: "#D4537E",
  lobby: "#EF9F27",
  service: "#1D9E75",
  bathroom: "#378ADD",
  stair: "#888780",
  elevator: "#888780",
};

function CoresLayer({ graph }: { graph: BuildingGraph }) {
  return (
    <g>
      {graph.cores.map((c) => {
        const pts = c.polygon.map((p) => p.join(",")).join(" ");
        const cx = c.polygon.reduce((s, p) => s + p[0], 0) / c.polygon.length;
        const cy = c.polygon.reduce((s, p) => s + p[1], 0) / c.polygon.length;
        return (
          <g key={c.id}>
            <defs>
              <pattern id={`hatch-${c.id}`} patternUnits="userSpaceOnUse" width={480} height={480} patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="480" stroke="rgba(0,106,106,0.5)" strokeWidth={40} />
              </pattern>
            </defs>
            <polygon
              points={pts}
              fill={`url(#hatch-${c.id})`}
              stroke="var(--secondary)"
              strokeWidth={80}
              strokeDasharray="160 120"
            />
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={400}
              fill="var(--secondary)"
              fontFamily="JetBrains Mono, monospace"
              letterSpacing={40}
              pointerEvents="none"
            >
              CORE
            </text>
          </g>
        );
      })}
    </g>
  );
}

function OpeningsLayer({ graph }: { graph: BuildingGraph }) {
  return (
    <g>
      {graph.openings.map((o) => {
        const w = graph.walls.find((w) => w.id === o.wallId);
        if (!w) return null;
        const mx = w.start[0] + (w.end[0] - w.start[0]) * o.tAlong;
        const my = w.start[1] + (w.end[1] - w.start[1]) * o.tAlong;
        return (
          <circle
            key={o.id}
            cx={mx}
            cy={my}
            r={o.widthMm / 2}
            fill="none"
            stroke={o.type === "door" ? "var(--secondary)" : "var(--fn-blue)"}
            strokeWidth={30}
            strokeDasharray="120 60"
            opacity={0.7}
            pointerEvents="none"
          />
        );
      })}
    </g>
  );
}

function DimensionsLayer({ graph }: { graph: BuildingGraph; structural?: StructuralGraph | null }) {
  const offset = 1800;
  const y = graph.widthMm + offset;
  return (
    <g>
      {graph.grid.xAxes.slice(0, -1).map((a, i) => {
        const next = graph.grid.xAxes[i + 1];
        const mid = (a.positionMm + next.positionMm) / 2;
        return (
          <g key={`dim-${a.label}`}>
            <line x1={a.positionMm} x2={next.positionMm} y1={y} y2={y} stroke="rgba(49,52,41,0.5)" strokeWidth={20} />
            <line x1={a.positionMm} x2={a.positionMm} y1={y - 100} y2={y + 100} stroke="rgba(49,52,41,0.5)" strokeWidth={20} />
            <line x1={next.positionMm} x2={next.positionMm} y1={y - 100} y2={y + 100} stroke="rgba(49,52,41,0.5)" strokeWidth={20} />
            <text x={mid} y={y - 140} textAnchor="middle" fontSize={260} fontFamily="JetBrains Mono" fill="var(--on-surface-variant)">
              {(next.positionMm - a.positionMm).toLocaleString()} mm
            </text>
          </g>
        );
      })}
    </g>
  );
}

function ColumnsLayer({
  candidates,
  overlayMode,
  supportFilter,
  selection,
  hover,
  onSelect,
  onHover,
}: {
  candidates: ReturnType<typeof Array>[number] extends never ? never : BuildingGraph["columnCandidates"];
  overlayMode: OverlayMode;
  supportFilter?: Record<SupportClass, boolean>;
  selection: { kind: ElementKind; id: string | null };
  hover: { kind: ElementKind; id: string | null };
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  const showScoreColors = overlayMode === "supports";
  return (
    <g>
      {(candidates as BuildingGraph["columnCandidates"]).map((c) => {
        if (supportFilter && !supportFilter[c.classification]) return null;
        const isSel = selection.kind === "column" && selection.id === c.id;
        const isH = hover.kind === "column" && hover.id === c.id;
        const palette = SUPPORT_COLOR[c.classification];
        const fill = showScoreColors
          ? c.classification === "weak" || c.classification === "forbidden"
            ? "transparent"
            : palette.dot
          : "var(--on-surface)";
        const stroke = showScoreColors ? palette.dot : "var(--on-surface)";
        const r = showScoreColors
          ? c.classification === "strong"
            ? 260
            : c.classification === "secondary"
              ? 220
              : 180
          : 200;
        return (
          <g
            key={c.id}
            data-el="column"
            onClick={() => onSelect(c.id)}
            onMouseEnter={() => onHover(c.id)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: "pointer" }}
          >
            {showScoreColors && c.classification === "forbidden" ? (
              <g>
                <line
                  x1={c.position[0] - 180}
                  y1={c.position[1] - 180}
                  x2={c.position[0] + 180}
                  y2={c.position[1] + 180}
                  stroke={stroke}
                  strokeWidth={80}
                />
                <line
                  x1={c.position[0] + 180}
                  y1={c.position[1] - 180}
                  x2={c.position[0] - 180}
                  y2={c.position[1] + 180}
                  stroke={stroke}
                  strokeWidth={80}
                />
              </g>
            ) : (
              <circle
                cx={c.position[0]}
                cy={c.position[1]}
                r={r * (isH ? 1.2 : 1)}
                fill={fill}
                stroke={stroke}
                strokeWidth={60}
              />
            )}
            {isSel && (
              <circle
                cx={c.position[0]}
                cy={c.position[1]}
                r={r + 240}
                fill="none"
                stroke="var(--secondary)"
                strokeWidth={80}
                className="pulse-ring"
              />
            )}
          </g>
        );
      })}
    </g>
  );
}

function ZonesLayer({
  zones,
  selection,
  hover,
  onSelect,
  onHover,
}: {
  zones: StructuralZone[];
  selection: { kind: ElementKind; id: string | null };
  hover: { kind: ElementKind; id: string | null };
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  return (
    <g>
      {zones.map((z) => {
        const info = ZONE_FILL[z.type];
        const pts = z.polygon.map((p) => p.join(",")).join(" ");
        const cx = z.polygon.reduce((s, p) => s + p[0], 0) / z.polygon.length;
        const cy = z.polygon.reduce((s, p) => s + p[1], 0) / z.polygon.length;
        const isSel = selection.kind === "zone" && selection.id === z.id;
        const isH = hover.kind === "zone" && hover.id === z.id;
        return (
          <g
            key={z.id}
            data-el="zone"
            onClick={() => onSelect(z.id)}
            onMouseEnter={() => onHover(z.id)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: "pointer" }}
          >
            <polygon
              points={pts}
              fill={info.fill}
              fillOpacity={isSel ? 0.42 : isH ? 0.3 : 0.2}
              stroke={info.stroke}
              strokeWidth={60}
              strokeDasharray="180 110"
            />
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={340}
              fill={info.stroke}
              fontFamily="Inter, sans-serif"
              fontWeight={500}
              letterSpacing={20}
              pointerEvents="none"
            >
              {info.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

// Export layer keys used by controls
export const LAYER_LABELS: Record<LayerKey, string> = {
  walls: "Walls",
  grid: "Grid",
  rooms: "Rooms",
  columns: "Columns",
  cores: "Cores",
  openings: "Openings",
  dimensions: "Dimensions",
};
