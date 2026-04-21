"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { PlanCanvas2D } from "@/components/canvas/PlanCanvas2D";
import { ModelCanvas3D } from "@/components/canvas/ModelCanvas3D";
import { CanvasControls } from "@/components/canvas/CanvasControls";
import { CanvasWorkspace } from "@/components/layout/CanvasWorkspace";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { PhaseGate } from "@/components/panels/PhaseGate";
import { AnalysisPanel } from "@/components/panels/AnalysisPanel";
import { InspectorPanel } from "@/components/panels/InspectorPanel";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  const viewMode = useCanvasStore((s) => s.viewMode);
  const setOverlayMode = useCanvasStore((s) => s.setOverlayMode);
  const [cursor, setCursor] = useState<{ x: number; y: number; z?: number } | null>(null);

  useEffect(() => {
    setOverlayMode("utilization");
    return () => setOverlayMode("none");
  }, [setOverlayMode]);

  const rightPanelTabs = useMemo(
    () =>
      project
        ? [
            { id: "analysis", label: "Analysis", content: <AnalysisPanel project={project} /> },
            { id: "inspector", label: "Inspector", content: <InspectorPanel project={project} /> },
          ]
        : [],
    [project],
  );

  if (!project) notFound();
  const graph = project.buildingGraph;
  if (!graph) {
    return (
      <div className="flex-1 flex items-center justify-center text-body-md text-on-surface-variant">
        Generate the building graph first.
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Analysis"
        projectName={project.name}
        subtitle={
          project.analysis
            ? `Max utilization ${(project.analysis.maxUtilization * 100).toFixed(0)}% · Drift ${project.analysis.driftStatus.toUpperCase()}`
            : undefined
        }
        actions={
          <button
            type="button"
            onClick={() => router.push(`/projects/${project.id}/summary`)}
            className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
          >
            Design summary
            <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
          </button>
        }
      />
      <PhaseGate project={project} requiredPhase={5}>
        <CanvasWorkspace
          canvas={
            <>
              {viewMode === "2d" ? (
                <PlanCanvas2D
                  graph={graph}
                  structural={project.structuralGraph}
                  overlayMode="utilization"
                  onCursor={(pt) => setCursor(pt ? { x: pt.x, y: pt.y } : null)}
                />
              ) : (
                <ModelCanvas3D
                  graph={graph}
                  structural={project.structuralGraph}
                  overlayMode="utilization"
                  onCursor={(pt) => setCursor(pt)}
                />
              )}
              <CanvasControls
                maxFloors={graph.stories}
                overlayModes={["utilization", "none"]}
              />
              <UtilizationLegend />
              <CursorReadout cursor={cursor} />
            </>
          }
          rightPanelTabs={rightPanelTabs}
        />
      </PhaseGate>
    </div>
  );
}

function UtilizationLegend() {
  return (
    <div className="absolute bottom-vs-3 left-vs-3 z-10 px-vs-3 py-vs-2 bg-surface-container-lowest/95 backdrop-blur-sm border-hairline rounded-sm text-body-sm">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-1">
        Utilization
      </div>
      <div
        className="h-[6px] w-[180px] rounded-full"
        style={{
          background:
            "linear-gradient(to right, var(--util-0), var(--util-50), var(--util-85), var(--util-95))",
        }}
      />
      <div className="flex justify-between font-mono text-[10px] text-on-surface-variant mt-[2px]">
        <span>0%</span>
        <span>50%</span>
        <span>85%</span>
        <span>100%</span>
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
    </div>
  );
}
