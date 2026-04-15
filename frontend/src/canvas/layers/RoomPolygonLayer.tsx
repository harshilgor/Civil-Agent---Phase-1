import { useJobStore } from "@/state/jobStore";

export function RoomPolygonLayer() {
  const rooms = useJobStore((s) => s.results?.rooms ?? []);
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {rooms.map((r) => (
        <div key={r.id} style={{ padding: 4, fontSize: 12 }}>
          Room {r.label} ({r.id})
        </div>
      ))}
    </div>
  );
}
