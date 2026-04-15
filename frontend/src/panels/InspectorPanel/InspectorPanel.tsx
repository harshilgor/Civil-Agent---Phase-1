import { RoomInspector } from "./RoomInspector";
import { WallInspector } from "./WallInspector";

export function InspectorPanel() {
  return (
    <div style={{ padding: 12 }}>
      <h3>Inspector</h3>
      <RoomInspector />
      <WallInspector />
    </div>
  );
}
