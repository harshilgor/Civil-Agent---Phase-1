import { useState } from "react";
import { patchScale } from "@/api/client";
import { useJobStore } from "@/state/jobStore";

export function ScalePanel({ jobId }: { jobId?: string }) {
  const scale = useJobStore((s) => s.results?.scale);
  const [mpp, setMpp] = useState(scale?.meters_per_pixel ?? 0.01);

  const apply = async () => {
    if (!jobId) return;
    await patchScale(jobId, mpp);
  };

  return (
    <div style={{ padding: 12 }}>
      <h3>Scale</h3>
      <p>
        Detected: {scale ? `${scale.meters_per_pixel} (${scale.source})` : "—"}
      </p>
      <label>
        m/px override{" "}
        <input
          type="number"
          step="0.0001"
          value={mpp}
          onChange={(e) => setMpp(Number(e.target.value))}
        />
      </label>
      <button type="button" onClick={() => void apply()}>
        Apply
      </button>
    </div>
  );
}
