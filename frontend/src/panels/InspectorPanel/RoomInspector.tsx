import { useSelectionStore } from "@/state/selectionStore";
import { useJobStore } from "@/state/jobStore";

export function RoomInspector() {
  const roomIds = useSelectionStore((s) => s.roomIds);
  const rooms = useJobStore((s) => s.results?.rooms ?? []);
  const r = rooms.find((x) => roomIds.includes(x.id));
  if (!r) return <p>No room selected</p>;
  return (
    <div>
      <h4>Room</h4>
      <p>
        {r.label} — confidence {r.confidence.toFixed(2)}
      </p>
    </div>
  );
}
