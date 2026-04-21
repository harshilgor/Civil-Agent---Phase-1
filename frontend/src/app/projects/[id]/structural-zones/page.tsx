"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { PlanCanvas2D } from "@/components/canvas/PlanCanvas2D";
import { ModelCanvas3D } from "@/components/canvas/ModelCanvas3D";
import { CanvasControls } from "@/components/canvas/CanvasControls";
import { CanvasWorkspace } from "@/components/layout/CanvasWorkspace";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { InspectorPanel } from "@/components/panels/InspectorPanel";
import { ZonesListPanel } from "@/components/panels/ZonesListPanel";
import { PhaseGate } from "@/components/panels/PhaseGate";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";

export default function StructuralZonesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  const runPhase3 = useProjectsStore((s) => s.runPhase3);
  const viewMode = useCanvasStore((s) => s.viewMode);
  const setOverlayMode = useCanvasStore((s) => s.setOverlayMode);
  const [cursor, setCursor] = useState<{ x: number; y: number; z?: number } | null>(null);

  useEffect(() => {
    setOverlayMode("zones");
    return () => setOverlayMode("none");
  }, [setOverlayMode]);

  const rightPanelTabs = useMemo(
    () =>
      project
        ? [
            { id: "zones", label: "Zones", content: <ZonesListPanel project={project} /> },
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

  const phase3Status = p.phaseStatus[3];

  async function handleRunPhase3() {
    toast.message("Phase 3 — Computing load paths…");
    await runPhase3(p.id);
    toast.success("Phase 3 complete. Load summary ready.");
    router.push(`/projects/${p.id}/load-paths`);
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Structural zones"
        projectName={p.name}
        subtitle={
          p.structuralGraph
            ? `${p.structuralGraph.zones.length} zones · ${p.structuralGraph.buildingRegularity}`
            : undefined
        }
        actions={
          <>
            <button
              type="button"
              onClick={() => router.push(`/projects/${p.id}/support-map`)}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              Support map
              <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
            </button>
            {phase3Status === "complete" ? (
              <button
                type="button"
                onClick={() => router.push(`/projects/${p.id}/load-paths`)}
                className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
              >
                Load paths
                <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleRunPhase3}
                disabled={phase3Status === "running"}
                className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable disabled:opacity-50"
              >
                {phase3Status === "running" ? (
                  <>
                    <span
                      className="w-[6px] h-[6px] rounded-full pulse-dot"
                      style={{ background: "var(--on-primary)" }}
                    />
                    Running Phase 3…
                  </>
                ) : (
                  <>
                    Compute load paths
                    <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
                  </>
                )}
              </button>
            )}
          </>
        }
      />
      <PhaseGate project={p} requiredPhase={2}>
        <CanvasWorkspace
          canvas={
            <>
              {viewMode === "2d" ? (
                <PlanCanvas2D
                  graph={graph}
                  structural={p.structuralGraph}
                  overlayMode="zones"
                  onCursor={(pt) => setCursor(pt ? { x: pt.x, y: pt.y } : null)}
                />
              ) : (
                <ModelCanvas3D
                  graph={graph}
                  structural={p.structuralGraph}
                  overlayMode="zones"
                  onCursor={(pt) => setCursor(pt)}
                />
              )}
              <CanvasControls maxFloors={graph.stories} overlayModes={["zones", "none"]} />
              <CursorReadout cursor={cursor} />
            </>
          }
          rightPanelTabs={rightPanelTabs}
        />
      </PhaseGate>
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
