"use client";

import { use, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { notFound } from "next/navigation";
import { ArrowRight, Eye, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { PlanCanvas2D } from "@/components/canvas/PlanCanvas2D";
import { ModelCanvas3D } from "@/components/canvas/ModelCanvas3D";
import { CanvasControls } from "@/components/canvas/CanvasControls";
import { CanvasWorkspace } from "@/components/layout/CanvasWorkspace";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { InspectorPanel } from "@/components/panels/InspectorPanel";
import { AssumptionsPanel } from "@/components/panels/AssumptionsPanel";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { formatPercent } from "@/lib/format";

export default function BuildingGraphPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  const regenerate = useProjectsStore((s) => s.regenerateGraph);
  const runPhase2 = useProjectsStore((s) => s.runPhase2);
  const viewMode = useCanvasStore((s) => s.viewMode);
  const [cursor, setCursor] = useState<{ x: number; y: number; z?: number } | null>(null);

  const graph = project?.buildingGraph;
  const structural = project?.structuralGraph ?? null;
  const rightPanelTabs = useMemo(
    () =>
      project
        ? [
            { id: "inspector", label: "Inspector", content: <InspectorPanel project={project} /> },
            { id: "assumptions", label: "Assumptions", content: <AssumptionsPanel project={project} /> },
          ]
        : [],
    [project],
  );

  if (!project) notFound();
  const p = project;
  if (!graph) {
    return (
      <div className="flex-1 flex items-center justify-center text-body-md text-on-surface-variant">
        No building graph for this project.
      </div>
    );
  }

  const phase2Status = p.phaseStatus[2];

  async function handleRunPhase2() {
    toast.message("Phase 2 — Running structural graph generation…");
    await runPhase2(p.id);
    toast.success("Phase 2 complete. Structural graph ready.");
    router.push(`/projects/${p.id}/structural-zones`);
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Building graph"
        projectName={p.name}
        subtitle={p.subtitle}
        badges={
          <div
            className="inline-flex items-center gap-vs-2 h-7 px-vs-2 rounded-sm border-hairline text-body-sm"
            title="Phase 1 completeness"
          >
            <span
              className="w-[6px] h-[6px] rounded-full"
              style={{
                background:
                  graph.completeness >= 0.9
                    ? "var(--score-strong)"
                    : graph.completeness >= 0.7
                      ? "var(--score-secondary)"
                      : "var(--score-forbidden)",
              }}
            />
            <span className="text-on-surface-variant">Phase 1</span>
            <span className="font-mono">{formatPercent(graph.completeness)}</span>
          </div>
        }
        actions={
          <>
            <button
              type="button"
              onClick={() => {
                regenerate(p.id);
                toast.success("Building graph regenerated.");
              }}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              <RefreshCw className="w-3 h-3" strokeWidth={1.5} />
              Regenerate
            </button>
            {phase2Status === "complete" ? (
              <button
                type="button"
                onClick={() => router.push(`/projects/${p.id}/structural-zones`)}
                className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
              >
                <Eye className="w-3 h-3" strokeWidth={1.5} />
                View zones
              </button>
            ) : (
              <button
                type="button"
                onClick={handleRunPhase2}
                disabled={phase2Status === "running"}
                className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable disabled:opacity-50"
              >
                {phase2Status === "running" ? (
                  <>
                    <span
                      className="w-[6px] h-[6px] rounded-full pulse-dot"
                      style={{ background: "var(--on-primary)" }}
                    />
                    Running Phase 2…
                  </>
                ) : (
                  <>
                    Generate structural graph
                    <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
                  </>
                )}
              </button>
            )}
          </>
        }
      />
      <CanvasWorkspace
        canvas={
          <>
            {viewMode === "2d" ? (
              <PlanCanvas2D
                graph={graph}
                structural={structural}
                onCursor={(pt) => setCursor(pt ? { x: pt.x, y: pt.y } : null)}
              />
            ) : (
              <ModelCanvas3D
                graph={graph}
                structural={structural}
                onCursor={(pt) => setCursor(pt)}
              />
            )}
            <CanvasControls maxFloors={graph.stories} overlayModes={["none"]} />
            <CursorReadout cursor={cursor} />
          </>
        }
        rightPanelTabs={rightPanelTabs}
      />
    </div>
  );
}

function CursorReadout({
  cursor,
}: {
  cursor: { x: number; y: number; z?: number } | null;
}) {
  if (!cursor) return null;
  return (
    <div className="absolute bottom-vs-3 right-vs-3 z-10 px-vs-2 py-[4px] bg-surface-container-lowest/90 backdrop-blur-sm border-hairline rounded-sm font-mono text-[11px] text-on-surface-variant">
      X {cursor.x.toFixed(2)}m · Y {cursor.y.toFixed(2)}m
      {cursor.z != null && ` · Z ${cursor.z.toFixed(2)}m`}
    </div>
  );
}
