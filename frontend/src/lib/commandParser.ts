import type { ProjectV2 } from "@/types/domain";

export type CommandAction =
  | { kind: "navigate"; route: string; message: string }
  | { kind: "canvas"; action: "set_2d" | "set_3d" | "set_floor" | "set_overlay" | "fit" | "zoom_in" | "zoom_out"; payload?: unknown; message: string }
  | { kind: "query"; message: string }
  | { kind: "mutation"; action: "move_column" | "change_wall_type" | "add_no_support"; payload: Record<string, unknown>; message: string }
  | { kind: "run_phase"; phase: 2 | 3 | 5; message: string }
  | { kind: "error"; message: string }
  | { kind: "info"; message: string };

export function parseCommand(
  input: string,
  project: ProjectV2 | null,
): CommandAction {
  const src = input.trim().toLowerCase();
  if (!src) return { kind: "error", message: "Please enter a command." };
  if (!project && /\b(move|change|show|run|go to|switch|fit)\b/.test(src))
    return {
      kind: "error",
      message: "Open a project first to use that command.",
    };

  // Navigation
  if (/show\s+(me\s+)?(the\s+)?structural\s+zones|go to zones/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/structural-zones`,
      message: "Navigated to Structural Zones.",
    };
  if (/show\s+(me\s+)?(the\s+)?support\s+map|go to supports?/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/support-map`,
      message: "Navigated to Support Map.",
    };
  if (/show\s+(me\s+)?load\s+path|go to loads?/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/load-paths`,
      message: "Navigated to Load Paths.",
    };
  if (/show\s+(me\s+)?analysis|go to analysis/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/analysis`,
      message: "Navigated to Analysis.",
    };
  if (/design\s+summary|go to summary/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/summary`,
      message: "Navigated to Design Summary.",
    };
  if (/building\s+graph|go to graph/.test(src))
    return {
      kind: "navigate",
      route: `/projects/${project!.id}/building-graph`,
      message: "Navigated to Building Graph.",
    };

  // Canvas
  if (/switch to 3d|3d view|show 3d/.test(src))
    return { kind: "canvas", action: "set_3d", message: "Switched to 3D." };
  if (/switch to 2d|2d view|show 2d|plan view/.test(src))
    return { kind: "canvas", action: "set_2d", message: "Switched to 2D plan." };
  if (/fit (all )?to screen|fit view/.test(src))
    return { kind: "canvas", action: "fit", message: "Fit to screen." };
  if (/zoom in/.test(src))
    return { kind: "canvas", action: "zoom_in", message: "Zoomed in." };
  if (/zoom out/.test(src))
    return { kind: "canvas", action: "zoom_out", message: "Zoomed out." };

  const floorMatch = src.match(/(?:go to|show|floor)\s+(\d{1,3}|all)/);
  if (floorMatch) {
    const v = floorMatch[1] === "all" ? "all" : parseInt(floorMatch[1], 10);
    return {
      kind: "canvas",
      action: "set_floor",
      payload: v,
      message: `Switched to floor ${v}.`,
    };
  }

  if (/show (only )?strong supports?/.test(src))
    return {
      kind: "canvas",
      action: "set_overlay",
      payload: "supports",
      message: "Showing support-score overlay.",
    };

  // Phase runs
  if (/run phase 2|start phase 2|run structural zones/.test(src))
    return { kind: "run_phase", phase: 2, message: "Queued Phase 2." };
  if (/run phase 3|run load (gen|generation)/.test(src))
    return { kind: "run_phase", phase: 3, message: "Queued Phase 3." };
  if (/run phase 5|run analysis/.test(src))
    return { kind: "run_phase", phase: 5, message: "Queued Phase 5." };

  // Queries
  const scoreMatch = src.match(/score of (?:column )?([a-z]-?\d{1,3}(?:-f\d{1,3})?)/);
  if (scoreMatch && project?.buildingGraph) {
    const target = scoreMatch[1].toUpperCase();
    const col = project.buildingGraph.columnCandidates.find(
      (c) =>
        c.id.toUpperCase().includes(target) ||
        c.gridIntersection.toUpperCase() === target,
    );
    if (col)
      return {
        kind: "query",
        message: `Column ${col.gridIntersection} · score ${col.score.toFixed(3)} · classification ${col.classification}.`,
      };
    return { kind: "query", message: `No column found matching "${target}".` };
  }

  if (/how many supports?|count supports?/.test(src) && project?.buildingGraph) {
    const n = project.buildingGraph.columnCandidates.filter(
      (c) => c.classification === "strong",
    ).length;
    return { kind: "query", message: `${n} strong support candidates across all floors.` };
  }

  if (/governing constraints?|what.*violat/.test(src) && project?.structuralGraph) {
    const violated = project.structuralGraph.constraints.filter(
      (c) => c.status === "violated",
    );
    const near = project.structuralGraph.constraints.filter(
      (c) => c.status === "partial",
    );
    if (violated.length === 0 && near.length === 0)
      return { kind: "query", message: "All hard constraints are met." };
    return {
      kind: "query",
      message:
        [
          violated.length ? `${violated.length} violated` : null,
          near.length ? `${near.length} partial` : null,
        ]
          .filter(Boolean)
          .join(", ") + " constraints. See Design Summary for details.",
    };
  }

  // Mutations
  const moveMatch = src.match(
    /move (?:column )?([a-z]-\d{1,3})\s+to\s+(\d{3,6})[,\s]+(\d{3,6})/,
  );
  if (moveMatch) {
    return {
      kind: "mutation",
      action: "move_column",
      payload: {
        columnId: moveMatch[1].toUpperCase(),
        x: parseInt(moveMatch[2], 10),
        y: parseInt(moveMatch[3], 10),
      },
      message: `Moved column ${moveMatch[1].toUpperCase()} to (${moveMatch[2]}, ${moveMatch[3]}).`,
    };
  }

  const wallMatch = src.match(
    /change (?:wall )?([wW]-?\d{1,3})\s+to\s+(structural|partition|shear)/,
  );
  if (wallMatch) {
    return {
      kind: "mutation",
      action: "change_wall_type",
      payload: {
        wallId: wallMatch[1].toUpperCase().replace(/^W(\d)/, "W-$1"),
        type: wallMatch[2],
      },
      message: `Changed wall ${wallMatch[1]} to ${wallMatch[2]}.`,
    };
  }

  return {
    kind: "info",
    message: `I understood: "${input}". That command is scheduled for the next planning iteration — try: "show support map", "go to floor 2", "switch to 3d", "run phase 2", or "score of column B-2".`,
  };
}

export const COMMAND_SUGGESTIONS = [
  "Move column B-3 to 8500, 18000",
  "Switch to 3D",
  "Show only strong supports",
  "Go to floor 2",
  "Run phase 2",
  "Score of column A-1",
  "Show structural zones",
  "What are the governing constraints?",
];
