"use client";

import type { ProjectV2 } from "@/types/domain";
import { formatKn } from "@/lib/format";

export function LoadsPanel({ project }: { project: ProjectV2 }) {
  const ls = project.loadSummary;
  if (!ls) {
    return (
      <div className="p-vs-4 text-body-sm text-on-surface-variant">
        Run Phase 3 to see the load summary.
      </div>
    );
  }
  return (
    <div className="p-vs-4 flex flex-col gap-vs-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Gravity loads
        </div>
        <div className="flex flex-col gap-vs-1 text-body-sm">
          <Row k="Dead load" v={`${ls.deadLoadKnM2.toFixed(1)} kN/m²`} />
          <Row k="Live load" v={`${ls.liveLoadKnM2.toFixed(1)} kN/m²`} />
          <Row k="Facade load" v={`${ls.facadeLoadKnM.toFixed(1)} kN/m`} />
          <Row k="Total weight" v={formatKn(ls.totalWeightKn)} />
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Lateral loads
        </div>
        <div className="flex flex-col gap-vs-1 text-body-sm">
          <Row k="Wind base · X" v={formatKn(ls.windBaseShearX)} />
          <Row k="Wind base · Y" v={formatKn(ls.windBaseShearY)} />
          <Row k="Seismic base · X" v={formatKn(ls.seismicBaseShearX)} />
          <Row k="Seismic base · Y" v={formatKn(ls.seismicBaseShearY)} />
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Governing combination
        </div>
        <div className="font-mono text-body-sm p-vs-2 bg-surface-container-low rounded-sm border-hairline">
          {ls.governingCombo}
        </div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mt-vs-3 mb-vs-2">
          Active combinations
        </div>
        <ul className="flex flex-col gap-vs-1 font-mono text-[11px] text-on-surface-variant">
          {ls.activeCombinations.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-vs-2">
      <span className="text-on-surface-variant">{k}</span>
      <span className="font-mono text-[11px]">{v}</span>
    </div>
  );
}
