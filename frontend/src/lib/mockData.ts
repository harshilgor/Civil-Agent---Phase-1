export type ProjectStatus =
  | "Verified (L1–L4)"
  | "Needs Review"
  | "Processing"
  | "Complete";

export type PipelineStage =
  | "awaiting_floor_plan"
  | "geometry_processing"
  | "geometry_ready";

export type Project = {
  id: string;
  name: string;
  code: string;
  areaM2: number;
  floors: number;
  status: ProjectStatus;
  confidencePct: number;
  lastRun: string;
  coreLabel: string;
  voidZones: number;
  transferRisk: "Low" | "Elevated" | "Critical";
  /** User-created projects use the pipeline; seed projects omit this (treated as ready). */
  pipelineStage?: PipelineStage;
  floorPlanFileName?: string | null;
  /** Extruded shell footprint in metres (mock-derived from plan). */
  footprint?: { w: number; d: number; h: number };
};

export type LayerKey = "spine" | "voids" | "flow" | "metadata";

export type GraphNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  role: "column" | "wall" | "core" | "span";
};

export type SpecLine = { label: string; value: string };

export const projects: Project[] = [
  {
    id: "helix-tower",
    name: "Helix Tower v2.4",
    code: "HTX-24",
    areaM2: 3850,
    floors: 24,
    status: "Verified (L1–L4)",
    confidencePct: 94.2,
    lastRun: "2026-04-16T14:22Z",
    coreLabel: "ZONE_ALPHA_TEAL",
    voidZones: 6,
    transferRisk: "Elevated",
  },
  {
    id: "meridian-pier",
    name: "Meridian Pier Annex",
    code: "MPA-11",
    areaM2: 12640,
    floors: 11,
    status: "Needs Review",
    confidencePct: 87.6,
    lastRun: "2026-04-15T09:05Z",
    coreLabel: "CORE_GRID_B",
    voidZones: 14,
    transferRisk: "Low",
  },
  {
    id: "kiln-house",
    name: "Kiln House Retrofit",
    code: "KHR-03",
    areaM2: 920,
    floors: 3,
    status: "Processing",
    confidencePct: 61.4,
    lastRun: "2026-04-14T22:41Z",
    coreLabel: "FLOW_CORRIDOR_PINK",
    voidZones: 2,
    transferRisk: "Critical",
  },
  {
    id: "gridline-7",
    name: "Gridline 7 Logistics Shell",
    code: "G7L-06",
    areaM2: 22100,
    floors: 6,
    status: "Complete",
    confidencePct: 99.1,
    lastRun: "2026-04-10T18:18Z",
    coreLabel: "VOID_PLATE_PURPLE",
    voidZones: 22,
    transferRisk: "Low",
  },
];

export function getProject(id: string): Project | undefined {
  return projects.find((p) => p.id === id);
}

export const graphNodes: GraphNode[] = [
  { id: "c1", label: "B-3", x: 120, y: 160, role: "column" },
  { id: "c2", label: "C-3", x: 220, y: 160, role: "column" },
  { id: "w1", label: "N-S", x: 120, y: 200, role: "wall" },
  { id: "core", label: "CORE", x: 320, y: 220, role: "core" },
  { id: "s1", label: "Span C-4", x: 220, y: 280, role: "span" },
];

export const planSpecs: SpecLine[] = [
  { label: "Grid Alignment", value: "0.992 (survey tie)" },
  { label: "Load Path", value: "Core-first, perimeter secondary" },
  { label: "Confidence Interval", value: "±1.1% (Monte Carlo n=4,200)" },
  { label: "Transfer Beam", value: "TB-C4-12m candidate" },
];

export const summaryAssumptions: string[] = [
  "All internal partitions are non-load bearing unless tagged.",
  "Foundation capacity assumes Class C soil profile.",
];

export const summaryWarnings: string[] = [
  "Span at Grid C-4 exceeds 12m limit. Transfer beam required or additional support candidate.",
];

export const terminalHistory: string[] = [
  "Terminal_Prompt > Move column B-3 to position 8500, 12000",
  "OK — grid alignment delta 0.004m within tolerance",
];

export const activeElementCoords = "X 8,500 · Y 12,000 · Z +0.000";

export const layerStateDefault: Record<LayerKey, boolean> = {
  spine: true,
  voids: true,
  flow: false,
  metadata: true,
};
