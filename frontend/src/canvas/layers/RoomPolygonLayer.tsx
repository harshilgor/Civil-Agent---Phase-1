import { useJobStore } from "@/state/jobStore";
import { useSelectionStore } from "@/state/selectionStore";

export function RoomPolygonLayer() {
  const results = useJobStore((s) => s.results);
  const rooms = results?.rooms ?? [];
  const metadata = results?.metadata ?? {};
  const imageW = Number(metadata.image_width ?? 1000);
  const imageH = Number(metadata.image_height ?? 1000);
  const selected = useSelectionStore((s) => s.roomIds);
  const setRooms = useSelectionStore((s) => s.setRooms);

  return (
    <svg
      viewBox={`0 0 ${imageW} ${imageH}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      {rooms.map((r) => {
        const pts = r.polygon.map((p) => `${p.x},${p.y}`).join(" ");
        const isSelected = selected.includes(r.id);
        return (
          <g key={r.id} onClick={() => setRooms([r.id])} style={{ cursor: "pointer" }}>
            <polygon
              points={pts}
              fill={isSelected ? "rgba(245, 158, 11, 0.35)" : "rgba(34, 197, 94, 0.25)"}
              stroke={isSelected ? "#f59e0b" : "#22c55e"}
              strokeWidth={isSelected ? 2 : 1.2}
            />
            {r.polygon[0] ? (
              <text
                x={r.polygon[0].x + 3}
                y={r.polygon[0].y + 12}
                fill="#e6edf3"
                fontSize={10}
                stroke="none"
              >
                {r.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
