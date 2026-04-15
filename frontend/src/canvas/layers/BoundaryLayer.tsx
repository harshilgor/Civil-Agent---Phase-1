import { useJobStore } from "@/state/jobStore";

export function BoundaryLayer() {
  const results = useJobStore((s) => s.results);
  const edges = results?.boundaries ?? [];
  const metadata = results?.metadata ?? {};
  const w = Number(metadata.image_width ?? 1000);
  const h = Number(metadata.image_height ?? 1000);

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
    >
      {edges.map((e, idx) => (
        <line
          key={`edge-${idx}`}
          x1={e.start.x}
          y1={e.start.y}
          x2={e.end.x}
          y2={e.end.y}
          stroke="#58a6ff"
          strokeWidth={1.5}
          strokeOpacity={Math.max(0.2, e.confidence ?? 0.6)}
        />
      ))}
    </svg>
  );
}
