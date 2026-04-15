import { exportJob } from "@/api/client";

export function ExportButton({ jobId }: { jobId?: string }) {
  const dl = async (fmt: "json" | "csv") => {
    if (!jobId) return;
    const blob = await exportJob(jobId, fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job-${jobId}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <span>
      <button type="button" onClick={() => void dl("json")}>
        Export JSON
      </button>
      <button type="button" onClick={() => void dl("csv")}>
        Export CSV
      </button>
    </span>
  );
}
