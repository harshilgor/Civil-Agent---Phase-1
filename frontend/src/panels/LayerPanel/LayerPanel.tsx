import { useCanvasStore } from "@/state/canvasStore";

const IDS = ["image", "rooms", "boundaries", "heatmap", "contested"] as const;

export function LayerPanel() {
  const layers = useCanvasStore((s) => s.layers);
  const toggle = useCanvasStore((s) => s.toggleLayer);
  return (
    <div style={{ padding: 12 }}>
      <h3>Layers</h3>
      {IDS.map((id) => (
        <label key={id} style={{ display: "block" }}>
          <input type="checkbox" checked={layers[id]} onChange={() => toggle(id)} /> {id}
        </label>
      ))}
    </div>
  );
}
