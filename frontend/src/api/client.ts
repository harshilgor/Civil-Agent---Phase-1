import type { JobSummary, PipelineResults } from "./types";

const base = () => import.meta.env.VITE_API_URL ?? "";

export async function uploadFloorplan(file: File): Promise<{ job_id: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${base()}/upload`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(jobId: string): Promise<JobSummary> {
  const res = await fetch(`${base()}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  const j = await res.json();
  return {
    id: j.id,
    status: j.status,
    progress_pct: j.progress_pct,
    current_stage: j.current_stage,
    error_message: j.error_message,
  };
}

export async function getResults(jobId: string): Promise<PipelineResults> {
  const res = await fetch(`${base()}/jobs/${jobId}/results`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function patchRoom(
  jobId: string,
  roomId: string,
  body: Record<string, unknown>,
): Promise<unknown> {
  const res = await fetch(`${base()}/jobs/${jobId}/rooms/${roomId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportJob(jobId: string, format: "json" | "geojson" | "csv"): Promise<Blob> {
  const res = await fetch(`${base()}/jobs/${jobId}/export?format=${format}`);
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function patchScale(jobId: string, metersPerPixel: number): Promise<unknown> {
  const res = await fetch(`${base()}/jobs/${jobId}/scale`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meters_per_pixel: metersPerPixel, source: "user" }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
