import { useCanvasStore } from "@/state/canvasStore";
import { BoundaryLayer } from "./layers/BoundaryLayer";
import { ConfidenceHeatmap } from "./layers/ConfidenceHeatmap";
import { ContestedZoneLayer } from "./layers/ContestedZoneLayer";
import { EditOverlay } from "./layers/EditOverlay";
import { ImageLayer } from "./layers/ImageLayer";
import { RoomPolygonLayer } from "./layers/RoomPolygonLayer";

export function FloorplanCanvas() {
  const layers = useCanvasStore((s) => s.layers);
  return (
    <div style={{ width: "100%", height: "100%", position: "relative", background: "#010409" }}>
      {layers.image ? <ImageLayer /> : null}
      {layers.boundaries ? <BoundaryLayer /> : null}
      {layers.rooms ? <RoomPolygonLayer /> : null}
      {layers.heatmap ? <ConfidenceHeatmap /> : null}
      {layers.contested ? <ContestedZoneLayer /> : null}
      <EditOverlay />
    </div>
  );
}
