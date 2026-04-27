"use client";

import { useState } from "react";
import { notFound, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Download, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { ViewHeader } from "@/components/layout/ViewHeader";
import {
  boardFeet,
  compareSizerLayouts,
  countSizerMembers,
  downloadBlob,
  exportSizerPdf,
  formatMoney,
  formatNumber,
  formatRatio,
  getSelectedSizerResult,
  governingCheck,
  materialLabel,
  memberTitle,
} from "@/lib/sizer";
import { useProjectsStore } from "@/stores/projectsStore";
import { useSizerUiStore } from "@/stores/sizerUiStore";
import type { ProjectV2, SizerLayout, SizerMemberResult, SizerResult } from "@/types/domain";

type SizerView = "overview" | "members" | "schemes" | "calculations" | "settings";

const sectionLabel =
  "text-[10px] uppercase tracking-[0.12em] font-mono text-on-surface-variant";
const tableHead =
  "grid px-vs-3 py-vs-2 border-b-hairline bg-surface-container-low text-[10px] uppercase tracking-[0.12em] text-on-surface-variant";
const darkButton =
  "h-8 inline-flex items-center gap-vs-2 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-md font-medium hover:opacity-90 pressable disabled:opacity-50";

export function SizerProjectScreen({
  projectId,
  view,
}: {
  projectId: string;
  view: SizerView;
}) {
  const project = useProjectsStore((s) => s.getProject(projectId));
  if (!project || project.projectType !== "wood_framing_sizer" || !project.sizerProject) {
    notFound();
  }
  const result = getSelectedSizerResult(project);
  if (!result) {
    notFound();
  }

  const title =
    view === "overview"
      ? "Overview"
      : view === "members"
        ? "Members"
        : view === "schemes"
          ? "Schemes"
          : view === "calculations"
            ? "Calculations"
            : "Settings";

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title={title}
        projectName={project.name}
        subtitle={`Layout ${result.layout} - NDS 2018 - ASCE 7-22`}
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        {view === "overview" && <Overview project={project} result={result} />}
        {view === "members" && <Members result={result} />}
        {view === "schemes" && <Schemes project={project} />}
        {view === "calculations" && <Calculations project={project} result={result} />}
        {view === "settings" && <SizerSettings project={project} />}
      </div>
      <SizerAssumptionsPanel project={project} result={result} />
    </div>
  );
}

function Overview({ project, result }: { project: ProjectV2; result: SizerResult }) {
  const router = useRouter();
  const [exporting, setExporting] = useState(false);
  const cost = result.summary.cost_estimate;

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await exportSizerPdf(result);
      downloadBlob(blob, `${project.name.replace(/[^a-z0-9_-]+/gi, "-")}-calculations.pdf`);
      toast.success("Calculation package exported.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1440px] px-vs-6 py-vs-6 grid grid-cols-1 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)] gap-vs-6">
      <section className="min-w-0 border-hairline rounded-sm bg-surface-container-lowest overflow-hidden">
        <div className="p-vs-4 border-b-hairline">
          <div className={sectionLabel}>Floor framing summary</div>
          <h1 className="font-headline text-title-lg font-medium mt-vs-1">{project.name}</h1>
          <p className="text-body-sm text-on-surface-variant">
            Layout {result.layout} - NDS 2018 - ASCE 7-22
          </p>
        </div>
        <div className={`${tableHead} grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_110px_80px]`}>
          <div>Member</div>
          <div>Size</div>
          <div>Governs</div>
          <div>Util</div>
        </div>
        <div className="divide-y divide-[rgba(49,52,41,0.08)]">
          {result.members.map((member) => (
            <button
              key={member.member_id}
              type="button"
              onClick={() =>
                router.push(`/projects/${project.id}/sizer/calculations?member=${member.member_id}`)
              }
              className="w-full grid grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_110px_80px] gap-vs-3 px-vs-3 py-vs-3 text-left items-center hover:bg-surface-container-low tonal-hover"
            >
              <div className="min-w-0">
                <div className="text-body-md font-medium truncate">{memberTitle(member)}</div>
                <div className="text-body-sm text-on-surface-variant font-mono">
                  {member.member_id}
                </div>
              </div>
              <div className="min-w-0">
                <div className="font-mono text-[12px] truncate">{materialLabel(member)}</div>
                <div className="text-body-sm text-on-surface-variant">
                  {member.spacing_in ? `@ ${member.spacing_in}" o.c.` : member.trace.span_config?.replace(/_/g, " ")}
                </div>
              </div>
              <div className="text-body-sm">{governingCheck(member)}</div>
              <UtilCell value={member.trace.final_utilization} warning={member.trace.warning} />
            </button>
          ))}
        </div>
        <ConnectorBlock result={result} />
      </section>

      <aside className="min-w-0 flex flex-col gap-vs-5">
        <MetaSection title="Project">
          <MetaRow label="Name" value={project.name} />
        </MetaSection>
        <MetaSection title="Codes">
          <MetaRow label="Design basis" value="NDS 2018 / IBC 2021 / ASCE 7-22" />
          <MetaRow label="Scope" value="Gravity loads only" />
        </MetaSection>
        <MetaSection title="Species / Grade">
          <MetaRow
            label="Wood"
            value={`${project.sizerProject?.inputParams.load_parameters.species} / ${project.sizerProject?.inputParams.load_parameters.grade}`}
          />
        </MetaSection>
        <MetaSection title="Quantities">
          <MetaRow label="Sawn lumber" value={`${boardFeet(result)} board-feet`} mono />
          <MetaRow label="Concrete" value={`${formatNumber(result.summary.concrete_volume_ft3)} cubic feet`} mono />
          <MetaRow label="Members" value={`${countSizerMembers(result)} total`} mono />
        </MetaSection>
        <MetaSection title="Estimated cost">
          <CostRow label="Lumber installed" value={formatMoney(cost?.lumber_installed_dollars)} />
          <CostRow label="Concrete" value={formatMoney(cost?.concrete_dollars)} />
          <CostRow label="Hardware" value={formatMoney(cost?.hardware_dollars)} />
          <div className="border-t-hairline mt-vs-2 pt-vs-2">
            <CostRow label="Total" value={formatMoney(cost?.total_dollars)} strong />
          </div>
        </MetaSection>
        <div className="flex flex-wrap gap-vs-2">
          <button
            type="button"
            onClick={() => router.push(`/projects/${project.id}/sizer/schemes`)}
            className={darkButton}
          >
            Compare layouts
            <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.5} />
          </button>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={exporting}
            className="h-8 inline-flex items-center gap-vs-2 px-vs-3 rounded-sm border-hairline text-body-md hover:bg-surface-container-low disabled:opacity-50"
          >
            {exporting ? <Loader2 className="w-3.5 h-3.5 spin-slow" /> : <Download className="w-3.5 h-3.5" />}
            Export calculations
          </button>
        </div>
      </aside>
    </div>
  );
}

function Members({ result }: { result: SizerResult }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <div className="mx-auto max-w-[1440px] px-vs-6 py-vs-6">
      <div className="border-hairline rounded-sm bg-surface-container-lowest overflow-hidden">
        <div className={`${tableHead} grid-cols-[150px_minmax(160px,1fr)_90px_110px_repeat(5,92px)]`}>
          <div>Member ID</div>
          <div>Selected</div>
          <div>Span</div>
          <div>Tributary</div>
          <div>Bending</div>
          <div>Shear</div>
          <div>Defl LL</div>
          <div>Defl TL</div>
          <div>Bearing</div>
        </div>
        <div className="divide-y divide-[rgba(49,52,41,0.08)]">
          {result.members.map((member) => (
            <div key={member.member_id}>
              <button
                type="button"
                onClick={() => setExpanded((current) => (current === member.member_id ? null : member.member_id))}
                className="w-full grid grid-cols-[150px_minmax(160px,1fr)_90px_110px_repeat(5,92px)] gap-vs-2 px-vs-3 py-vs-3 text-left items-center hover:bg-surface-container-low tonal-hover"
              >
                <span className="font-mono text-[12px]">{member.member_id}</span>
                <span className="font-mono text-[12px] truncate">{materialLabel(member)}</span>
                <span className="font-mono text-[12px]">{member.span_ft ? `${member.span_ft} ft` : "-"}</span>
                <span className="font-mono text-[12px]">{loadValue(member, "tributary width")}</span>
                {["bending", "shear", "deflection LL", "deflection TL", "bearing"].map((name) => (
                  <span key={name} className="font-mono text-[12px]">
                    {formatRatio(findCheck(member, name)?.ratio)}
                  </span>
                ))}
              </button>
              {expanded === member.member_id && (
                <div className="border-t-hairline bg-surface px-vs-4 py-vs-4">
                  <CalculationTrace member={member} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Schemes({ project }: { project: ProjectV2 }) {
  const router = useRouter();
  const setComparison = useProjectsStore((s) => s.setSizerComparison);
  const updateSizerProject = useProjectsStore((s) => s.updateSizerProject);
  const setSizingInProgress = useSizerUiStore((s) => s.setSizingInProgress);
  const [loading, setLoading] = useState(false);
  const sizer = project.sizerProject;
  if (!sizer) return null;
  const inputParams = sizer.inputParams;
  const layoutA = sizer.layoutAResult;
  const layoutB = sizer.layoutBResult;

  async function runCompare() {
    setLoading(true);
    setSizingInProgress(true);
    try {
      const comparison = await compareSizerLayouts(inputParams);
      setComparison(project.id, comparison);
      toast.success("Layout comparison sized.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Comparison failed.");
    } finally {
      setLoading(false);
      setSizingInProgress(false);
    }
  }

  function proceed(layout: SizerLayout) {
    updateSizerProject(project.id, { selectedLayout: layout });
    router.push(`/projects/${project.id}/sizer/overview`);
  }

  if (!layoutA || !layoutB) {
    return (
      <div className="mx-auto max-w-[760px] px-vs-6 py-vs-8 flex flex-col gap-vs-4">
        <div className={sectionLabel}>Scheme comparison</div>
        <h1 className="font-headline text-title-lg font-medium">{project.name}</h1>
        <p className="text-body-md text-on-surface-variant">
          Size both layouts to compare joist depth, beams, footings, quantities, and estimated cost.
        </p>
        <button type="button" onClick={() => void runCompare()} disabled={loading} className={darkButton}>
          {loading ? <Loader2 className="w-3.5 h-3.5 spin-slow" /> : <ArrowRight className="w-3.5 h-3.5" />}
          Size Layout A / Layout B
        </button>
      </div>
    );
  }

  const costA = layoutA.summary.cost_estimate?.total_dollars ?? 0;
  const costB = layoutB.summary.cost_estimate?.total_dollars ?? 0;
  const savings = Math.abs(costA - costB);
  const cheaper = costA <= costB ? "A" : "B";
  const lumberDeltaPct = boardFeet(layoutA)
    ? Math.round((Math.abs(boardFeet(layoutA) - boardFeet(layoutB)) / boardFeet(layoutA)) * 100)
    : 0;

  return (
    <div className="mx-auto max-w-[1100px] px-vs-6 py-vs-6 flex flex-col gap-vs-5">
      <div>
        <div className={sectionLabel}>Scheme comparison</div>
        <h1 className="font-headline text-title-lg font-medium mt-vs-1">{project.name}</h1>
      </div>
      <div className="border-hairline rounded-sm bg-surface-container-lowest overflow-hidden">
        <div className={`${tableHead} grid-cols-[170px_1fr_1fr]`}>
          <div />
          <div>Layout A - Perimeter support</div>
          <div>Layout B - Centre beam</div>
        </div>
        <SchemeRow label="Joists" a={schemeMember(layoutA, "joist")} b={schemeMember(layoutB, "joist")} />
        <SchemeRow label="Beam" a="-" b={schemeMember(layoutB, "beam")} />
        <SchemeRow label="Column" a="-" b={schemeMember(layoutB, "column")} />
        <SchemeRow label="Sawn lumber" a={`${boardFeet(layoutA)} board-feet`} b={`${boardFeet(layoutB)} board-feet`} />
        <SchemeRow label="Concrete" a={`${formatNumber(layoutA.summary.concrete_volume_ft3)} cubic feet`} b={`${formatNumber(layoutB.summary.concrete_volume_ft3)} cubic feet`} />
        <SchemeRow label="Total est." a={formatMoney(costA)} b={formatMoney(costB)} strong />
      </div>
      <p className="text-title-sm text-on-surface">
        Layout {cheaper} saves {formatMoney(savings)}. Layout B uses about {lumberDeltaPct}% less sawn lumber and introduces a beam and column.
      </p>
      <div className="flex flex-wrap gap-vs-2">
        <button type="button" onClick={() => proceed("A")} className={darkButton}>
          Proceed with Layout A
        </button>
        <button type="button" onClick={() => proceed("B")} className={darkButton}>
          Proceed with Layout B
        </button>
      </div>
    </div>
  );
}

function Calculations({ project, result }: { project: ProjectV2; result: SizerResult }) {
  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("member") ?? result.members[0]?.member_id;
  const member = result.members.find((item) => item.member_id === selectedId) ?? result.members[0];
  return (
    <div className="mx-auto max-w-[980px] px-vs-6 py-vs-6 print:p-0">
      <div className="mb-vs-4 flex items-center gap-vs-3 print:hidden">
        <label className="flex items-center gap-vs-2">
          <span className={sectionLabel}>Member</span>
          <select
            value={member.member_id}
            onChange={(e) =>
              router.push(`/projects/${project.id}/sizer/calculations?member=${e.target.value}`)
            }
            className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary text-body-md font-mono"
          >
            {result.members.map((item) => (
              <option key={item.member_id} value={item.member_id}>
                {item.member_id}
              </option>
            ))}
          </select>
        </label>
      </div>
      <CalculationTrace member={member} fullPage />
    </div>
  );
}

function SizerSettings({ project }: { project: ProjectV2 }) {
  const sizer = project.sizerProject;
  if (!sizer) return null;
  return (
    <div className="max-w-[720px] px-vs-6 py-vs-6 flex flex-col gap-vs-6">
      <MetaSection title="Project">
        <MetaRow label="Project ID" value={project.id} mono />
        <MetaRow label="Type" value="Wood Framing - Sizer" />
        <MetaRow label="Selected layout" value={sizer.selectedLayout ?? "-"} mono />
      </MetaSection>
      <MetaSection title="Input">
        <MetaRow label="Room length" value={`${sizer.inputParams.dimensions.length_ft} ft`} mono />
        <MetaRow label="Room width" value={`${sizer.inputParams.dimensions.width_ft} ft`} mono />
        <MetaRow label="Dead load" value={`${sizer.inputParams.load_parameters.dead_load_psf} psf`} mono />
        <MetaRow label="Live load" value={`${sizer.inputParams.load_parameters.live_load_psf} psf`} mono />
      </MetaSection>
    </div>
  );
}

function CalculationTrace({
  member,
  fullPage = false,
}: {
  member: SizerMemberResult;
  fullPage?: boolean;
}) {
  return (
    <article className={["bg-surface-container-lowest border-hairline rounded-sm", fullPage ? "print:border-0" : ""].join(" ")}>
      <div className="p-vs-4 border-b-hairline">
        <h2 className="font-headline text-title-md font-medium">
          {member.member_id} - {materialLabel(member)} - Span {member.span_ft ?? member.length_ft ?? "-"} ft
        </h2>
      </div>
      <TraceSection title="Loads" rows={member.trace.loads.map((item) => [item.name, item.value, item.unit, item.source])} />
      <TraceSection title="Section properties" rows={member.trace.section_properties.map((item) => [item.name, item.value, item.unit, item.source])} />
      <TraceSection title="Reference design values" rows={member.trace.reference_design_values.map((item) => [item.name, item.value, item.unit, item.source])} />
      <AdjustmentSection member={member} />
      <CodeChecks member={member} />
      <div className="px-vs-4 py-vs-3 border-t-hairline text-body-sm">
        <span className="font-medium">Governing:</span>{" "}
        <span className="font-mono">{governingCheck(member)} at {formatRatio(member.trace.final_utilization)}</span>
      </div>
      <style jsx>{`
        @media print {
          article {
            break-inside: avoid;
            page-break-inside: avoid;
          }
        }
      `}</style>
    </article>
  );
}

function TraceSection({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, number | string | boolean, string | null | undefined, string]>;
}) {
  if (!rows.length) return null;
  return (
    <section className="px-vs-4 py-vs-3 border-t-hairline">
      <div className={`${sectionLabel} mb-vs-2`}>{title}</div>
      <div className="grid gap-vs-1">
        {rows.map(([name, value, unit, source]) => (
          <div key={`${title}-${name}`} className="grid grid-cols-[minmax(160px,1fr)_120px_70px_minmax(180px,1fr)] gap-vs-3 text-body-sm">
            <div>{name}</div>
            <div className="font-mono text-right">{formatNumber(value)}</div>
            <div className="font-mono text-on-surface-variant">{unit ?? ""}</div>
            <div className="text-on-surface-variant text-right truncate">{source}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AdjustmentSection({ member }: { member: SizerMemberResult }) {
  if (!member.trace.adjustment_factors.length) return null;
  return (
    <section className="px-vs-4 py-vs-3 border-t-hairline">
      <div className={`${sectionLabel} mb-vs-2`}>Adjustment factors</div>
      <div className="grid gap-vs-1">
        {member.trace.adjustment_factors.map((factor) => (
          <div key={factor.symbol} className="grid grid-cols-[48px_80px_minmax(160px,1fr)_minmax(180px,1fr)] gap-vs-3 text-body-sm">
            <div className="font-mono">{factor.symbol}</div>
            <div className="font-mono text-right">{formatNumber(factor.value)}</div>
            <div>{factor.name}</div>
            <div className="text-on-surface-variant text-right truncate">{factor.source}</div>
          </div>
        ))}
      </div>
      {member.trace.adjusted_design_values.map((value) => (
        <div key={value.name} className="mt-vs-2 font-mono text-[12px] text-on-surface">
          {value.name} = reference value x {member.trace.adjustment_factors.map((f) => f.value.toFixed(2)).join(" x ")} = {formatNumber(value.value)} {value.unit}
        </div>
      ))}
    </section>
  );
}

function CodeChecks({ member }: { member: SizerMemberResult }) {
  if (!member.trace.checks.length) return null;
  return (
    <section className="px-vs-4 py-vs-3 border-t-hairline">
      <div className={`${sectionLabel} mb-vs-2`}>Code checks</div>
      <div className="grid grid-cols-[minmax(130px,1fr)_120px_120px_80px_40px] gap-vs-3 text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-1">
        <div />
        <div className="text-right">Demand</div>
        <div className="text-right">Capacity</div>
        <div className="text-right">Ratio</div>
        <div />
      </div>
      <div className="grid gap-vs-1">
        {member.trace.checks.map((check) => (
          <div key={check.name} className="grid grid-cols-[minmax(130px,1fr)_120px_120px_80px_40px] gap-vs-3 text-body-sm">
            <div>{check.name}</div>
            <div className="font-mono text-right">{formatNumber(check.demand)} {check.unit}</div>
            <div className="font-mono text-right">{formatNumber(check.capacity)} {check.unit}</div>
            <div className="font-mono text-right">{formatRatio(check.ratio)}</div>
            <div style={{ color: check.passed ? "var(--success)" : "var(--error)" }}>{check.passed ? "✓" : "✗"}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SizerAssumptionsPanel({ project, result }: { project: ProjectV2; result: SizerResult }) {
  const open = useSizerUiStore((s) => s.assumptionsOpen);
  const setOpen = useSizerUiStore((s) => s.setAssumptionsOpen);
  const rows = [
    ["Dead load", `${project.sizerProject?.inputParams.load_parameters.dead_load_psf} psf`, "Project input"],
    ["Live load", `${project.sizerProject?.inputParams.load_parameters.live_load_psf} psf`, "ASCE 7-22 Table 4.3-1"],
    ["Dry service condition", "CM = 1.0", "NDS Table 2.3.1"],
    ["Normal temperature", "Ct = 1.0", "NDS Table 2.3.3"],
    ["Soil bearing pressure", "1,500 psf", "IBC 2021 Table 1806.2"],
    ["Bearing length at supports", "1.5 in", "Project default"],
    ["Column end conditions", "Pinned-pinned", "Project default"],
    ["Auto-upsize threshold", "0.90 util.", "Civil Agent design margin"],
    ["Connector loads", "Requires verification", "Requires verification"],
    ...result.assumptions.map((item) => [item.description, "", item.source]),
  ];
  if (!open) return null;
  return (
    <aside className="absolute top-0 right-0 bottom-0 w-[420px] max-w-[95vw] border-l-hairline bg-surface-container-lowest shadow-elev-floating z-40 flex flex-col">
      <div className="h-12 px-vs-4 border-b-hairline flex items-center justify-between">
        <div>
          <div className={sectionLabel}>Assumptions register</div>
          <div className="text-body-sm text-on-surface-variant truncate">{project.name}</div>
        </div>
        <button type="button" onClick={() => setOpen(false)} className="w-7 h-7 rounded-sm hover:bg-surface-container inline-flex items-center justify-center">
          <X className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-vs-4">
        <div className="grid grid-cols-[minmax(140px,1fr)_100px_120px] gap-vs-2 text-[10px] uppercase tracking-[0.12em] text-on-surface-variant border-b-hairline pb-vs-2 mb-vs-2">
          <div>Assumption</div>
          <div>Value</div>
          <div>Source</div>
        </div>
        <div className="grid gap-vs-2">
          {rows.map(([assumption, value, source], index) => (
            <div key={`${assumption}-${index}`} className="grid grid-cols-[minmax(140px,1fr)_100px_120px] gap-vs-2 text-body-sm">
              <div>{source === "Requires verification" && <span style={{ color: "var(--warning)" }}>⚠ </span>}{assumption}</div>
              <div className="font-mono text-[11px]">{value}</div>
              <div className="text-on-surface-variant">{source}</div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

function ConnectorBlock({ result }: { result: SizerResult }) {
  const connectors = result.members.flatMap((member) =>
    Object.entries(member.trace.connections ?? {}).map(([key, connector]) => ({
      key: `${member.member_id}-${key}`,
      name: connector.interface,
      product: connector.product,
      util: connector.utilisation,
      warning: connector.warning,
    })),
  );
  if (!connectors.length) return null;
  return (
    <div className="border-t-hairline p-vs-4">
      <div className={`${sectionLabel} mb-vs-2`}>Connectors</div>
      <div className="grid gap-vs-2">
        {connectors.map((connector) => (
          <div key={connector.key} className="grid grid-cols-[minmax(160px,1fr)_140px_80px] gap-vs-3 text-body-sm">
            <div>{connector.name}</div>
            <div className="font-mono text-[12px]">{connector.product}</div>
            <div>{connector.warning ? <span style={{ color: "var(--warning)" }}>⚠ verify</span> : formatRatio(connector.util)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function UtilCell({ value, warning }: { value: number; warning?: string | null }) {
  const color = value >= 0.9 ? "var(--error)" : value >= 0.75 ? "var(--warning)" : "";
  return (
    <span className="inline-flex items-center gap-vs-2 font-mono text-[12px]">
      {color && <span className="w-[6px] h-[6px] rounded-full" style={{ background: color }} />}
      {warning ? <span style={{ color: "var(--warning)" }}>⚠ </span> : null}
      {formatRatio(value)}
    </span>
  );
}

function MetaSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t-hairline pt-vs-3">
      <div className={`${sectionLabel} mb-vs-2`}>{title}</div>
      <div className="grid gap-vs-1">{children}</div>
    </section>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-vs-4 text-body-sm">
      <span className="text-on-surface-variant">{label}</span>
      <span className={mono ? "font-mono text-[12px] text-right" : "text-right"}>{value}</span>
    </div>
  );
}

function CostRow({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={["flex items-baseline justify-between gap-vs-4 text-body-sm", strong ? "font-medium" : ""].join(" ")}>
      <span className="text-on-surface-variant">{label}</span>
      <span className="font-mono text-[12px] text-right">{value}</span>
    </div>
  );
}

function SchemeRow({
  label,
  a,
  b,
  strong,
}: {
  label: string;
  a: string;
  b: string;
  strong?: boolean;
}) {
  return (
    <div className={["grid grid-cols-[170px_1fr_1fr] gap-vs-3 px-vs-3 py-vs-3 border-t-hairline text-body-sm", strong ? "font-medium" : ""].join(" ")}>
      <div className="text-on-surface-variant">{label}</div>
      <div className="font-mono text-[12px] whitespace-pre-line">{a}</div>
      <div className="font-mono text-[12px] whitespace-pre-line">{b}</div>
    </div>
  );
}

function schemeMember(result: SizerResult, type: string): string {
  const member = result.members.find((item) => item.member_type === type);
  if (!member) return "-";
  return `${materialLabel(member)}\n${governingCheck(member)} ${formatRatio(member.trace.final_utilization)}`;
}

function loadValue(member: SizerMemberResult, name: string): string {
  const item = member.trace.loads.find((load) => load.name === name);
  if (!item) return "-";
  return `${formatNumber(item.value)} ${item.unit}`;
}

function findCheck(member: SizerMemberResult, name: string) {
  const normalized = name.toLowerCase();
  return member.trace.checks.find((check) => check.name.toLowerCase() === normalized);
}
