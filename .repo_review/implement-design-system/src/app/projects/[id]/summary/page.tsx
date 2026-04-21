"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { notFound } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowLeft,
  Copy,
  Download,
  FileJson,
  FileText,
  FileType,
  Image as ImageIcon,
  Printer,
} from "lucide-react";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { useProjectsStore } from "@/stores/projectsStore";
import { formatKn, formatM, formatPercent } from "@/lib/format";
import type { ProjectV2 } from "@/types/domain";

export default function DesignSummaryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));

  if (!project) notFound();
  const p: ProjectV2 = project;
  const graph = p.buildingGraph;
  const sg = p.structuralGraph;
  const ls = p.loadSummary;
  const an = p.analysis;

  function downloadBlob(
    content: string,
    filename: string,
    mime: string,
  ) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    downloadBlob(
      JSON.stringify(p, null, 2),
      `${p.id}.civil-agent.json`,
      "application/json",
    );
    toast.success("JSON exported.");
  }

  function exportMarkdown() {
    const md = buildMarkdown(p);
    downloadBlob(md, `${p.id}.design-summary.md`, "text/markdown");
    toast.success("Markdown report exported.");
  }

  function copyHandoff() {
    const md = buildMarkdown(p);
    navigator.clipboard.writeText(md);
    toast.success("Design handoff copied to clipboard.");
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <ViewHeader
        title="Design summary"
        projectName={p.name}
        subtitle={p.subtitle}
        actions={
          <>
            <button
              type="button"
              onClick={() => router.push(`/projects/${p.id}/building-graph`)}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              <ArrowLeft className="w-3 h-3" strokeWidth={1.5} />
              Back to canvas
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              <Printer className="w-3 h-3" strokeWidth={1.5} />
              Print
            </button>
            <button
              type="button"
              onClick={copyHandoff}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
            >
              <Copy className="w-3 h-3" strokeWidth={1.5} />
              Copy handoff
            </button>
          </>
        }
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        <div className="mx-auto max-w-[940px] px-vs-6 py-vs-6">
          <div className="flex items-start justify-between mb-vs-6 gap-vs-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-1">
                Civil Agent · Design handoff
              </div>
              <h1 className="text-display-md mb-vs-1">{p.name}</h1>
              <p className="text-body-md text-on-surface-variant">
                {p.subtitle} · {p.input.locationText}
              </p>
            </div>
            <div className="flex flex-col gap-vs-2">
              <ExportChip label="PDF" icon={FileText} onClick={exportMarkdown} />
              <ExportChip label="Markdown" icon={FileType} onClick={exportMarkdown} />
              <ExportChip label="JSON" icon={FileJson} onClick={exportJson} />
              <ExportChip label="IFC / DXF" icon={ImageIcon} disabled />
            </div>
          </div>

          <section className="mb-vs-6">
            <SectionTitle>Design inputs</SectionTitle>
            <div className="grid grid-cols-4 gap-vs-3">
              <Kv k="Length" v={formatM(p.input.lengthM * 1000, 1)} />
              <Kv k="Width" v={formatM(p.input.widthM * 1000, 1)} />
              <Kv k="Stories" v={`${p.input.stories}`} />
              <Kv k="Story height" v={formatM(p.input.typicalFloorHeightM * 1000, 1)} />
              <Kv k="Occupancy" v={p.input.occupancy.replace("_", " ")} />
              <Kv k="Material" v={p.input.material.toUpperCase()} />
              <Kv k="Core" v={p.input.coreLocation.replace("_", " ")} />
              <Kv k="Code" v={p.input.buildingCode.replace("_", " ")} />
            </div>
          </section>

          {graph && (
            <section className="mb-vs-6">
              <SectionTitle>Building graph</SectionTitle>
              <div className="grid grid-cols-4 gap-vs-3">
                <Kv k="Completeness" v={formatPercent(graph.completeness)} accent />
                <Kv k="Walls" v={`${graph.walls.length}`} />
                <Kv k="Rooms" v={`${graph.rooms.length}`} />
                <Kv k="Column candidates" v={`${graph.columnCandidates.filter((c) => c.floor === 1).length}/floor`} />
              </div>
            </section>
          )}

          {sg && (
            <section className="mb-vs-6">
              <SectionTitle>Structural zones</SectionTitle>
              <div className="grid grid-cols-4 gap-vs-3">
                <Kv k="Zones" v={`${sg.zones.length}`} />
                <Kv k="Regularity" v={sg.buildingRegularity} />
                <Kv
                  k="Typical span"
                  v={`${(sg.typicalSpanMm / 1000).toFixed(1)} m`}
                />
                <Kv k="Framing direction" v={sg.framingDirection.toUpperCase()} />
              </div>
              <div className="mt-vs-4">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
                  Gravity system candidates
                </div>
                <ul className="flex flex-col divide-hairline border-hairline rounded-sm">
                  {sg.gravitySystemCandidates.map((c) => (
                    <li key={c.id} className="flex items-center justify-between p-vs-3">
                      <div>
                        <div className="text-body-md">
                          {c.system.replace(/_/g, " ").toUpperCase()}
                        </div>
                        <div className="text-body-sm text-on-surface-variant">
                          {c.rationale}
                        </div>
                      </div>
                      <div className="font-mono text-[13px] text-on-surface-variant">
                        {(c.plausibility * 100).toFixed(0)}%
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-vs-4">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
                  Lateral system candidates
                </div>
                <ul className="flex flex-col divide-hairline border-hairline rounded-sm">
                  {sg.lateralSystemCandidates.map((c) => (
                    <li key={c.id} className="flex items-center justify-between p-vs-3">
                      <div>
                        <div className="text-body-md">
                          {c.system.replace(/_/g, " ").toUpperCase()}
                        </div>
                        <div className="text-body-sm text-on-surface-variant">
                          {c.location} · {c.rationale}
                        </div>
                      </div>
                      <div className="font-mono text-[13px] text-on-surface-variant">
                        {(c.plausibility * 100).toFixed(0)}%
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {ls && (
            <section className="mb-vs-6">
              <SectionTitle>Loads</SectionTitle>
              <div className="grid grid-cols-4 gap-vs-3">
                <Kv k="Dead" v={`${ls.deadLoadKnM2.toFixed(1)} kN/m²`} />
                <Kv k="Live" v={`${ls.liveLoadKnM2.toFixed(1)} kN/m²`} />
                <Kv k="Wind base·X" v={formatKn(ls.windBaseShearX)} />
                <Kv k="Seismic base·X" v={formatKn(ls.seismicBaseShearX)} />
                <Kv k="Total weight" v={formatKn(ls.totalWeightKn)} />
                <Kv k="Governing" v={ls.governingCombo} mono />
              </div>
            </section>
          )}

          {an && (
            <section className="mb-vs-6">
              <SectionTitle>Analysis</SectionTitle>
              <div className="grid grid-cols-4 gap-vs-3">
                <Kv k="Members" v={`${an.membersTotal}`} />
                <Kv
                  k="Passing"
                  v={`${an.membersPassing} / ${an.membersTotal}`}
                  accent={an.membersPassing === an.membersTotal}
                />
                <Kv k="Max utilization" v={formatPercent(an.maxUtilization)} />
                <Kv
                  k="Drift"
                  v={`${an.maxDriftRatio} (${an.driftStatus.toUpperCase()})`}
                  fail={an.driftStatus === "fail"}
                />
              </div>
              {an.membersFailing.length > 0 && (
                <ul className="mt-vs-3 flex flex-col divide-hairline border-hairline rounded-sm">
                  {an.membersFailing.map((m, i) => (
                    <li key={i} className="flex items-center justify-between p-vs-3 text-body-sm">
                      <span className="font-mono">{m.elementId}</span>
                      <span className="uppercase text-[10px] tracking-[0.08em] text-on-surface-variant">
                        {m.check}
                      </span>
                      <span className="font-mono" style={{ color: "var(--score-forbidden)" }}>
                        {m.ratio.toFixed(2)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {graph && (
            <section className="mb-vs-6">
              <SectionTitle>Assumptions</SectionTitle>
              <ul className="flex flex-col gap-vs-2 text-body-md text-on-surface-variant list-disc pl-vs-4">
                {graph.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </section>
          )}

          <div className="mt-vs-6 pt-vs-4 border-t-hairline flex items-center gap-vs-2 justify-end">
            <button
              type="button"
              onClick={exportJson}
              className="inline-flex items-center gap-vs-1 h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              <Download className="w-3 h-3" strokeWidth={1.5} />
              Download JSON
            </button>
            <button
              type="button"
              onClick={exportMarkdown}
              className="inline-flex items-center gap-vs-1 h-8 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
            >
              <Download className="w-3 h-3" strokeWidth={1.5} />
              Download report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-title-md mb-vs-3 pb-vs-2 border-b-hairline">{children}</h2>
  );
}

function Kv({
  k,
  v,
  mono,
  accent,
  fail,
}: {
  k: string;
  v: string;
  mono?: boolean;
  accent?: boolean;
  fail?: boolean;
}) {
  return (
    <div className="flex flex-col gap-[2px] p-vs-3 bg-surface-container-low border-hairline rounded-sm">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
        {k}
      </div>
      <div
        className={[
          mono ? "font-mono text-[13px]" : "text-body-lg",
          accent ? "text-[var(--score-strong)]" : "",
          fail ? "text-[var(--score-forbidden)]" : "",
        ].join(" ")}
      >
        {v}
      </div>
    </div>
  );
}

function ExportChip({
  label,
  icon: Icon,
  onClick,
  disabled,
}: {
  label: string;
  icon: typeof FileText;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-vs-2 h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm disabled:opacity-50"
    >
      <Icon className="w-3 h-3" strokeWidth={1.5} />
      {label}
    </button>
  );
}

function buildMarkdown(p: ProjectV2): string {
  const lines: string[] = [];
  lines.push(`# ${p.name}`);
  lines.push("");
  lines.push(`_${p.subtitle} · ${p.input.locationText}_`);
  lines.push("");
  lines.push(`## Design inputs`);
  lines.push(`- Length × Width: ${p.input.lengthM}m × ${p.input.widthM}m`);
  lines.push(`- Stories: ${p.input.stories}`);
  lines.push(`- Story height: ${p.input.typicalFloorHeightM}m`);
  lines.push(`- Occupancy: ${p.input.occupancy}`);
  lines.push(`- Material: ${p.input.material.toUpperCase()}`);
  lines.push(`- Core: ${p.input.coreLocation}`);
  lines.push(`- Code: ${p.input.buildingCode}`);
  if (p.buildingGraph) {
    lines.push("");
    lines.push(`## Building graph`);
    lines.push(`- Completeness: ${Math.round(p.buildingGraph.completeness * 100)}%`);
    lines.push(`- Walls: ${p.buildingGraph.walls.length}`);
    lines.push(`- Rooms: ${p.buildingGraph.rooms.length}`);
    lines.push(`- Column candidates (per floor): ${p.buildingGraph.columnCandidates.filter((c) => c.floor === 1).length}`);
  }
  if (p.structuralGraph) {
    lines.push("");
    lines.push(`## Structural zones`);
    for (const z of p.structuralGraph.zones) {
      lines.push(`- ${z.type} · floor ${z.floor} · ${z.areaM2} m²`);
    }
  }
  if (p.loadSummary) {
    lines.push("");
    lines.push(`## Loads`);
    lines.push(`- Governing: ${p.loadSummary.governingCombo}`);
    lines.push(`- Total weight: ${p.loadSummary.totalWeightKn} kN`);
  }
  if (p.analysis) {
    lines.push("");
    lines.push(`## Analysis`);
    lines.push(`- Max utilization: ${Math.round(p.analysis.maxUtilization * 100)}%`);
    lines.push(`- Drift: ${p.analysis.maxDriftRatio} (${p.analysis.driftStatus})`);
    lines.push(`- Deflection: ${p.analysis.maxSlabDeflection} (${p.analysis.deflectionStatus})`);
  }
  return lines.join("\n");
}
