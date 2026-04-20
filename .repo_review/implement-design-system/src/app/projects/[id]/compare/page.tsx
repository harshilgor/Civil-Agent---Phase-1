"use client";

import { use, useMemo, useState } from "react";
import { notFound } from "next/navigation";
import { ArrowLeftRight } from "lucide-react";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { PlanCanvas2D } from "@/components/canvas/PlanCanvas2D";
import { useProjectsStore } from "@/stores/projectsStore";
import { formatKn, formatPercent } from "@/lib/format";
import type { ProjectV2 } from "@/types/domain";

export default function ComparePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const project = useProjectsStore((s) => s.getProject(id));
  const getAll = useProjectsStore((s) => s.getAll);
  const all = getAll();
  const [leftId, setLeftId] = useState<string>(id);
  const [rightId, setRightId] = useState<string>(
    all.find((p) => p.id !== id)?.id ?? id,
  );

  const left = useMemo(() => all.find((p) => p.id === leftId) ?? null, [all, leftId]);
  const right = useMemo(
    () => all.find((p) => p.id === rightId) ?? null,
    [all, rightId],
  );

  if (!project) notFound();

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Compare"
        projectName={project.name}
        subtitle="Side-by-side iteration comparison"
      />
      <div className="flex-1 min-h-0 flex">
        <ComparisonColumn
          project={left}
          onChange={setLeftId}
          options={all}
          label="Left"
        />
        <div className="w-px bg-[var(--outline-variant)]" />
        <ComparisonColumn
          project={right}
          onChange={setRightId}
          options={all}
          label="Right"
        />
      </div>
    </div>
  );
}

function ComparisonColumn({
  project,
  onChange,
  options,
  label,
}: {
  project: ProjectV2 | null;
  onChange: (id: string) => void;
  options: ProjectV2[];
  label: string;
}) {
  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className="h-9 shrink-0 border-b-hairline flex items-center gap-vs-2 px-vs-3 bg-surface-container-low">
        <span className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          {label}
        </span>
        <select
          value={project?.id ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 h-7 text-body-sm px-vs-2 border-hairline rounded-sm bg-surface outline-none"
        >
          {options.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 relative bg-canvas-grid">
          {project?.buildingGraph ? (
            <PlanCanvas2D graph={project.buildingGraph} structural={project.structuralGraph} />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-body-sm text-on-surface-variant">
              No graph
            </div>
          )}
        </div>
        {project && (
          <div className="shrink-0 border-t-hairline bg-surface p-vs-3 grid grid-cols-3 gap-vs-2 text-body-sm">
            <Metric k="Completeness" v={formatPercent(project.phase1Completeness)} />
            <Metric
              k="Max util."
              v={project.analysis ? formatPercent(project.analysis.maxUtilization) : "—"}
            />
            <Metric
              k="Weight"
              v={project.loadSummary ? formatKn(project.loadSummary.totalWeightKn) : "—"}
            />
            <Metric k="Stories" v={`${project.input.stories}`} />
            <Metric k="Material" v={project.input.material.toUpperCase()} />
            <Metric k="Core" v={project.input.coreLocation.replace("_", " ")} />
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-on-surface-variant">{k}</span>
      <span className="font-mono text-[11px]">{v}</span>
    </div>
  );
}
