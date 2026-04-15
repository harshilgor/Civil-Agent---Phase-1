import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadFloorplan } from "@/api/client";
import { DropZone } from "./DropZone";

export function UploadPage() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"light" | "deep">("light");
  const [busy, setBusy] = useState(false);

  const submit = async (file: File) => {
    setBusy(true);
    try {
      void mode;
      const { job_id } = await uploadFloorplan(file);
      nav(`/processing/${job_id}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 560, margin: "48px auto", padding: 16 }}>
      <h1>Upload floor plan</h1>
      <label>
        Mode{" "}
        <select value={mode} onChange={(e) => setMode(e.target.value as "light" | "deep")}>
          <option value="light">Light</option>
          <option value="deep">Deep</option>
        </select>
      </label>
      <DropZone onFile={(f) => void submit(f)} />
      {busy ? <p>Uploading…</p> : null}
    </div>
  );
}
