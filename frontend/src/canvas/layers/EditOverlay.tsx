import { useCanvasStore } from "@/state/canvasStore";

export function EditOverlay() {
  const mode = useCanvasStore((s) => s.mode);
  if (mode === "select") return null;
  return (
    <div style={{ position: "absolute", inset: 0, outline: "1px dashed #58a6ff" }}>
      Edit: {mode}
    </div>
  );
}
