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
import { InspectorPanel } from "@/components/panels/InspectorPanel";
import { SupportsPanel } from "@/components/panels/SupportsPanel";
import { PhaseGate } from "@/components/panels/PhaseGate";
import type { SupportClass } from "@/types/domain";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";

export default function SupportMapPage({
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
  const [filter, setFilter] = useState<Record<SupportClass, boolean>>({
    strong: true,
    secondary: true,
    weak: true,
    forbidden: true,
  });

  useEffect(() => {
    setOverlayMode("supports");
    return () => setOverlayMode("none");
  }, [setOverlayMode]);

  const rightPanelTabs = useMemo(
    () =>
      project
        ? [
            {
              id: "supports",
              label: "Supports",
              content: (
                <SupportsPanel
                  project={project}
                  filter={filter}
                  onFilterChange={setFilter}
                />
              ),
            },
            { id: "inspector", label: "Inspector", content: <InspectorPanel project={project} /> },
          ]
        : [],
    [project, filter],
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

  const counts = graph.columnCandidates
    .filter((c) => c.floor === 1)
    .reduce<Record<SupportClass, number>>(
      (acc, c) => {
        acc[c.classification]++;
        return acc;
      },
      { strong: 0, secondary: 0, weak: 0, forbidden: 0 },
    );

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Support map"
        projectName={project.name}
        subtitle={`${counts.strong} strong · ${counts.secondary} secondary · ${counts.weak} weak · ${counts.forbidden} forbidden`}
        actions={
          <button
            type="button"
            onClick={() => router.push(`/projects/${project.id}/load-paths`)}
            className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
          >
            Load paths
            <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
          </button>
        }
      />
      <PhaseGate project={project} requiredPhase={2}>
        <CanvasWorkspace
          canvas={
            <>
              {viewMode === "2d" ? (
                <PlanCanvas2D
                  graph={graph}
                  structural={project.structuralGraph}
                  overlayMode="supports"
                  supportFilter={filter}
                  onCursor={(pt) => setCursor(pt ? { x: pt.x, y: pt.y } : null)}
                />
              ) : (
                <ModelCanvas3D
                  graph={graph}
                  structural={project.structuralGraph}
                  overlayMode="supports"
                  supportFilter={filter}
                  onCursor={(pt) => setCursor(pt)}
                />
              )}
              <CanvasControls
                maxFloors={graph.stories}
                overlayModes={["supports", "none"]}
              />
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
