import type { Project, PipelineStage } from "@/lib/mockData";

export type { PipelineStage };

export function isGeometryReady(project: Project): boolean {
  const stage: PipelineStage = project.pipelineStage ?? "geometry_ready";
  return stage === "geometry_ready";
}

export function pipelineLabel(project: Project): string {
  const stage = project.pipelineStage ?? "geometry_ready";
  if (stage === "awaiting_floor_plan") return "Awaiting floor plan upload";
  if (stage === "geometry_processing") return "Deriving 3D shell from floor plan";
  return "3D geometry synchronized";
}
