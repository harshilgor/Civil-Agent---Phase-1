/** Types mirroring backend pipeline / API payloads (extend as schemas stabilize). */

export type JobStatus = "queued" | "running" | "completed" | "failed";

export interface JobSummary {
  id: string;
  status: JobStatus;
  progress_pct: number;
  current_stage: string | null;
  error_message?: string | null;
}

export interface Point2D {
  x: number;
  y: number;
}

export interface RoomRegion {
  id: string;
  label: string;
  polygon: Point2D[];
  confidence: number;
}

export interface Edge {
  start: Point2D;
  end: Point2D;
  confidence: number;
}

export interface ScaleResult {
  meters_per_pixel: number;
  source: string;
  confidence: number;
}

export interface PipelineResults {
  pipeline: Record<string, unknown>;
  rooms: RoomRegion[];
  boundaries: Edge[];
  scale: ScaleResult | null;
  metadata: Record<string, unknown>;
}
