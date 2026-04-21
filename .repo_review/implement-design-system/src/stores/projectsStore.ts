"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  AnalysisResult,
  BuildingGraph,
  LoadSummary,
  PhaseId,
  PhaseStatus,
  ProjectStatus,
  ProjectV2,
  StructuralGraph,
  StructuredInput,
} from "@/types/domain";
import { defaultStructuredInput } from "@/lib/graph/nlParser";
import { generateBuildingGraph } from "@/lib/graph/buildingGraphGen";
import {
  generateAnalysis,
  generateLoadSummary,
  generateStructuralGraph,
} from "@/lib/graph/structuralGraphGen";

function nowIso() {
  return new Date().toISOString();
}

const SEED_TIMESTAMPS: Record<string, string> = {
  "helix-tower": "2026-04-18T08:30:42.618Z",
  "meridian-pier": "2026-04-18T08:30:42.624Z",
  "kiln-house": "2026-04-18T08:30:42.625Z",
  "gridline-7": "2026-04-18T08:30:42.626Z",
};

function makeSeed(
  id: string,
  name: string,
  buildingType: string,
  subtitle: string,
  input: Partial<StructuredInput>,
  phaseStatus: Record<PhaseId, PhaseStatus>,
  status: ProjectStatus,
): ProjectV2 {
  const finalInput: StructuredInput = {
    ...defaultStructuredInput(),
    buildingName: name,
    ...input,
  };
  const bg = generateBuildingGraph(id, finalInput);
  const sg =
    phaseStatus[2] === "complete" ? generateStructuralGraph(bg, finalInput) : null;
  const ls =
    phaseStatus[3] === "complete" ? generateLoadSummary(bg, finalInput) : null;
  const an = phaseStatus[5] === "complete" ? generateAnalysis(bg) : null;
  const createdAt = SEED_TIMESTAMPS[id] ?? "2026-04-18T08:30:00.000Z";
  const updatedAt = createdAt;
  return {
    id,
    name,
    buildingType,
    subtitle,
    source: "STRUCTURED",
    createdAt,
    updatedAt,
    status,
    phase1Completeness: bg.completeness,
    phase2Confidence: sg ? 0.88 : 0,
    phaseStatus,
    pipelineStage:
      phaseStatus[5] === "complete"
        ? "phase_5_complete"
        : phaseStatus[3] === "complete"
          ? "phase_3_complete"
          : phaseStatus[2] === "complete"
            ? "phase_2_complete"
            : phaseStatus[1] === "complete"
              ? "graph_building"
              : "awaiting_input",
    input: finalInput,
    buildingGraph: bg,
    structuralGraph: sg,
    loadSummary: ls,
    analysis: an,
  };
}

function allComplete(): Record<PhaseId, PhaseStatus> {
  return { 1: "complete", 2: "complete", 3: "complete", 4: "not_started", 5: "complete" };
}

function thruPhase(p: PhaseId): Record<PhaseId, PhaseStatus> {
  const s: Record<PhaseId, PhaseStatus> = {
    1: "not_started",
    2: "not_started",
    3: "not_started",
    4: "not_started",
    5: "not_started",
  };
  for (let i = 1; i <= p; i++) s[i as PhaseId] = "complete";
  return s;
}

const SEED_PROJECTS: ProjectV2[] = [
  makeSeed(
    "helix-tower",
    "Helix Tower V2.4",
    "Office, 6 stories",
    "Reinforced concrete, central core",
    {
      lengthM: 40,
      widthM: 25,
      stories: 6,
      typicalFloorHeightM: 3.9,
      occupancy: "office",
      material: "rc",
      coreLocation: "central",
      locationText: "San Francisco, CA",
      seismicZone: "D",
      windSpeedMph: 85,
      preferredBayXM: 8,
      preferredBayYM: 9,
    },
    allComplete(),
    "COMPLETE",
  ),
  makeSeed(
    "meridian-pier",
    "Meridian Pier Annex",
    "Mixed-use, 11 stories",
    "PT slab, edge-east core",
    {
      lengthM: 48,
      widthM: 22,
      stories: 11,
      occupancy: "mixed_use",
      material: "rc",
      coreLocation: "edge_east",
      locationText: "Seattle, WA",
      seismicZone: "D",
      preferredBayXM: 9,
      preferredBayYM: 8,
    },
    thruPhase(2),
    "NEEDS_REVIEW",
  ),
  makeSeed(
    "kiln-house",
    "Kiln House Retrofit",
    "Residential, 3 stories",
    "Timber frame, retrofit",
    {
      lengthM: 18,
      widthM: 12,
      stories: 3,
      occupancy: "residential",
      material: "timber",
      coreLocation: "corner",
      locationText: "Portland, OR",
      preferredBayXM: 6,
      preferredBayYM: 6,
    },
    { 1: "complete", 2: "running", 3: "not_started", 4: "not_started", 5: "not_started" },
    "PROCESSING",
  ),
  makeSeed(
    "gridline-7",
    "Gridline 7 Logistics",
    "Industrial, 6 stories",
    "Steel beam-column, no core",
    {
      lengthM: 80,
      widthM: 40,
      stories: 6,
      occupancy: "industrial",
      material: "steel",
      coreLocation: "none",
      locationText: "Chicago, IL",
      preferredBayXM: 10,
      preferredBayYM: 10,
    },
    allComplete(),
    "COMPLETE",
  ),
];

type ProjectsState = {
  userProjects: ProjectV2[];
  _hydrated: boolean;
  createProject: (input: StructuredInput, name?: string) => string;
  deleteProject: (id: string) => void;
  duplicateProject: (id: string) => string | null;
  renameProject: (id: string, name: string) => void;
  updateProject: (id: string, patch: Partial<ProjectV2>) => void;
  updateInput: (id: string, patch: Partial<StructuredInput>) => void;
  setPhase: (id: string, phase: PhaseId, status: PhaseStatus) => void;
  runPhase2: (id: string) => Promise<void>;
  runPhase3: (id: string) => Promise<void>;
  runPhase5: (id: string) => Promise<void>;
  regenerateGraph: (id: string) => void;
  moveColumn: (id: string, columnId: string, newPos: [number, number]) => void;
  setWallType: (id: string, wallId: string, type: "structural" | "partition" | "shear") => void;
  getProject: (id: string) => ProjectV2 | undefined;
  getAll: () => ProjectV2[];
};

function normalizeId(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 40) || "project";
  return `${base}-${Math.random().toString(36).slice(2, 7)}`;
}

export const useProjectsStore = create<ProjectsState>()(
  persist(
    (set, get) => ({
      userProjects: [],
      _hydrated: false,

      createProject: (input, name) => {
        const finalName = (name ?? input.buildingName ?? "Untitled project").trim() || "Untitled project";
        const id = normalizeId(finalName);
        const bg = generateBuildingGraph(id, input);
        const project: ProjectV2 = {
          id,
          name: finalName,
          buildingType: `${input.occupancy.replace("_", " ")}, ${input.stories} stories`,
          subtitle: `${input.material === "rc" ? "Reinforced concrete" : input.material === "steel" ? "Structural steel" : input.material} · ${input.coreLocation.replace("_", " ")} core`,
          source: "STRUCTURED",
          createdAt: nowIso(),
          updatedAt: nowIso(),
          status: "PROCESSING",
          phase1Completeness: bg.completeness,
          phase2Confidence: 0,
          phaseStatus: {
            1: "complete",
            2: "not_started",
            3: "not_started",
            4: "not_started",
            5: "not_started",
          },
          pipelineStage: "graph_building",
          input,
          buildingGraph: bg,
          structuralGraph: null,
          loadSummary: null,
          analysis: null,
        };
        set((s) => ({ userProjects: [project, ...s.userProjects] }));
        return id;
      },

      deleteProject: (id) =>
        set((s) => ({ userProjects: s.userProjects.filter((p) => p.id !== id) })),

      duplicateProject: (id) => {
        const p = get().getProject(id);
        if (!p) return null;
        const newId = normalizeId(p.name + " copy");
        const clone: ProjectV2 = {
          ...p,
          id: newId,
          name: p.name + " (copy)",
          createdAt: nowIso(),
          updatedAt: nowIso(),
        };
        set((s) => ({ userProjects: [clone, ...s.userProjects] }));
        return newId;
      },

      renameProject: (id, name) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) =>
            p.id === id ? { ...p, name, updatedAt: nowIso() } : p,
          ),
        })),

      updateProject: (id, patch) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) =>
            p.id === id ? { ...p, ...patch, updatedAt: nowIso() } : p,
          ),
        })),

      updateInput: (id, patch) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) =>
            p.id === id ? { ...p, input: { ...p.input, ...patch }, updatedAt: nowIso() } : p,
          ),
        })),

      setPhase: (id, phase, status) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) =>
            p.id === id
              ? {
                  ...p,
                  phaseStatus: { ...p.phaseStatus, [phase]: status },
                  updatedAt: nowIso(),
                }
              : p,
          ),
        })),

      regenerateGraph: (id) => {
        const p = get().getProject(id);
        if (!p) return;
        const bg = generateBuildingGraph(p.id, p.input);
        set((s) => ({
          userProjects: s.userProjects.map((u) =>
            u.id === id
              ? { ...u, buildingGraph: bg, phase1Completeness: bg.completeness, updatedAt: nowIso() }
              : u,
          ),
        }));
      },

      runPhase2: async (id) => {
        get().setPhase(id, 2, "running");
        await new Promise((r) => setTimeout(r, 1500));
        const p = get().getProject(id);
        if (!p || !p.buildingGraph) return;
        const sg = generateStructuralGraph(p.buildingGraph, p.input);
        set((s) => ({
          userProjects: s.userProjects.map((u) =>
            u.id === id
              ? {
                  ...u,
                  structuralGraph: sg,
                  phase2Confidence: 0.88,
                  phaseStatus: { ...u.phaseStatus, 2: "complete" },
                  pipelineStage: "phase_2_complete",
                  status: "COMPLETE",
                  updatedAt: nowIso(),
                }
              : u,
          ),
        }));
      },

      runPhase3: async (id) => {
        get().setPhase(id, 3, "running");
        await new Promise((r) => setTimeout(r, 1200));
        const p = get().getProject(id);
        if (!p || !p.buildingGraph) return;
        const ls = generateLoadSummary(p.buildingGraph, p.input);
        set((s) => ({
          userProjects: s.userProjects.map((u) =>
            u.id === id
              ? {
                  ...u,
                  loadSummary: ls,
                  phaseStatus: { ...u.phaseStatus, 3: "complete" },
                  pipelineStage: "phase_3_complete",
                  updatedAt: nowIso(),
                }
              : u,
          ),
        }));
      },

      runPhase5: async (id) => {
        get().setPhase(id, 5, "running");
        await new Promise((r) => setTimeout(r, 1600));
        const p = get().getProject(id);
        if (!p || !p.buildingGraph) return;
        const an = generateAnalysis(p.buildingGraph);
        set((s) => ({
          userProjects: s.userProjects.map((u) =>
            u.id === id
              ? {
                  ...u,
                  analysis: an,
                  phaseStatus: { ...u.phaseStatus, 5: "complete" },
                  pipelineStage: "phase_5_complete",
                  updatedAt: nowIso(),
                }
              : u,
          ),
        }));
      },

      moveColumn: (id, columnId, newPos) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) => {
            if (p.id !== id || !p.buildingGraph) return p;
            const cc = p.buildingGraph.columnCandidates.map((c) =>
              c.id === columnId ? { ...c, position: newPos } : c,
            );
            return {
              ...p,
              buildingGraph: { ...p.buildingGraph, columnCandidates: cc },
              updatedAt: nowIso(),
            };
          }),
        })),

      setWallType: (id, wallId, type) =>
        set((s) => ({
          userProjects: s.userProjects.map((p) => {
            if (p.id !== id || !p.buildingGraph) return p;
            const walls = p.buildingGraph.walls.map((w) =>
              w.id === wallId ? { ...w, type } : w,
            );
            return {
              ...p,
              buildingGraph: { ...p.buildingGraph, walls },
              updatedAt: nowIso(),
            };
          }),
        })),

      getProject: (id) => {
        const seed = SEED_PROJECTS.find((p) => p.id === id);
        if (seed) return seed;
        return get().userProjects.find((p) => p.id === id);
      },
      getAll: () => [...SEED_PROJECTS, ...get().userProjects],
    }),
    {
      name: "civil-agent-projects-v2",
      partialize: (s) => ({ userProjects: s.userProjects }),
      onRehydrateStorage: () => (state) => {
        if (state) state._hydrated = true;
      },
    },
  ),
);

export const SEED = SEED_PROJECTS;
