import type { DragEvent } from "react";

type Props = {
  onFile: (f: File) => void;
};

export function DropZone({ onFile }: Props) {
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };
  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      style={{
        border: "2px dashed #30363d",
        borderRadius: 8,
        padding: 48,
        textAlign: "center",
      }}
    >
      <p>Drag floor plan (PNG / JPG / PDF) here</p>
      <input
        type="file"
        accept="image/*,.pdf"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
    </div>
  );
}
