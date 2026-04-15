import { useCanvasStore } from "@/state/canvasStore";

export function ModeSwitcher() {
  const mode = useCanvasStore((s) => s.mode);
  const setMode = useCanvasStore((s) => s.setMode);
  return (
    <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
      <option value="select">Select</option>
      <option value="edit_vertices">Edit vertices</option>
      <option value="split">Split</option>
      <option value="merge">Merge</option>
    </select>
  );
}
