"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { notFound } from "next/navigation";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";
import { ModelCanvas3D } from "@/components/canvas/ModelCanvas3D";
import { PlanCanvas2D } from "@/components/canvas/PlanCanvas2D";
import { CanvasControls } from "@/components/canvas/CanvasControls";
import { CanvasWorkspace } from "@/components/layout/CanvasWorkspace";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { PhaseGate } from "@/components/panels/PhaseGate";
import { LoadsPanel } from "@/components/panels/LoadsPanel";
import { InspectorPanel } from "@/components/panels/InspectorPanel";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";

export default function LoadPathsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  const runPhase5 = useProjectsStore((s) => s.runPhase5);
  const viewMode = useCanvasStore((s) => s.viewMode);
  const setViewMode = useCanvasStore((s) => s.setViewMode);
  const setOverlayMode = useCanvasStore((s) => s.setOverlayMode);
  const [cursor, setCursor] = useState<{ x: number; y: number; z?: number } | null>(null);

  useEffect(() => {
    setOverlayMode("load_paths");
    setViewMode("3d");
    return () => setOverlayMode("none");
  }, [setOverlayMode, setViewMode]);

  const rightPanelTabs = useMemo(
    () =>
      project
        ? [
            { id: "loads", label: "Loads", content: <LoadsPanel project={project} /> },
            { id: "inspector", label: "Inspector", content: <InspectorPanel project={project} /> },
          ]
        : [],
    [project],
  );

  if (!project) notFound();
  const p = project;
  const graph = p.buildingGraph;
  if (!graph) {
    return (
      <div className="flex-1 flex items-center justify-center text-body-md text-on-surface-variant">
        Generate the building graph first.
      </div>
    );
  }
  const phase5Status = p.phaseStatus[5];

  async function handleRunPhase5() {
    toast.message("Phase 5 — Running analysis…");
    await runPhase5(p.id);
    toast.success("Phase 5 complete. Analysis ready.");
    router.push(`/projects/${p.id}/analysis`);
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Load paths"
        projectName={p.name}
        subtitle={p.loadSummary ? `Governing · ${p.loadSummary.governingCombo}` : undefined}
        actions={
          phase5Status === "complete" ? (
            <button
              type="button"
              onClick={() => router.push(`/projects/${p.id}/analysis`)}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
            >
              Analysis
              <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleRunPhase5}
              disabled={phase5Status === "running"}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable disabled:opacity-50"
            >
              {phase5Status === "running" ? (
                <>
                  <span
                    className="w-[6px] h-[6px] rounded-full pulse-dot"
                    style={{ background: "var(--on-primary)" }}
                  />
                  Running Phase 5…
                </>
              ) : (
                <>
                  Run analysis
                  <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
                </>
              )}
            </button>
          )
        }
      />
      <PhaseGate project={p} requiredPhase={3}>
        <CanvasWorkspace
          canvas={
            <>
              {viewMode === "3d" ? (
                <ModelCanvas3D
                  graph={graph}
                  structural={p.structuralGraph}
                  overlayMode="load_paths"
                  onCursor={(pt) => setCursor(pt)}
                />
              ) : (
                <PlanCanvas2D
                  graph={graph}
                  structural={p.structuralGraph}
                  onCursor={(pt) => setCursor(pt ? { x: pt.x, y: pt.y } : null)}
                />
              )}
              <CanvasControls maxFloors={graph.stories} overlayModes={["load_paths", "none"]} />
              <LegendLoadPaths />
              <CursorReadout cursor={cursor} />
            </>
          }
          rightPanelTabs={rightPanelTabs}
        />
      </PhaseGate>
    </div>
  );
}

function LegendLoadPaths() {
  return (
    <div className="absolute bottom-vs-3 left-vs-3 z-10 px-vs-3 py-vs-2 bg-surface-container-lowest/95 backdrop-blur-sm border-hairline rounded-sm text-body-sm">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-1">
        Axial load
      </div>
      <div className="h-[6px] w-[160px] rounded-full" style={{ background: "linear-gradient(to right, #97C459, #EF9F27, #D85A30)" }} />
      <div className="flex justify-between font-mono text-[10px] text-on-surface-variant mt-[2px]">
        <span>low</span>
        <span>high</span>
      </div>
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
