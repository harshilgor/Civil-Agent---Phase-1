"use client";

import { AlertTriangle, Check } from "lucide-react";
import type { ProjectV2 } from "@/types/domain";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { formatPercent } from "@/lib/format";

export function AnalysisPanel({ project }: { project: ProjectV2 }) {
  const a = project.analysis;
  if (!a) {
    return (
      <div className="p-vs-4 text-body-sm text-on-surface-variant">
        Run Phase 5 to see analysis results.
      </div>
    );
  }
  return (
    <div className="p-vs-4 flex flex-col gap-vs-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Member check
        </div>
        <div className="flex items-end gap-vs-2 mb-vs-2">
          <div className="font-mono text-[28px] leading-none">
            {formatPercent(a.membersPassing / a.membersTotal)}
          </div>
          <div className="text-body-sm text-on-surface-variant mb-[4px]">
            {a.membersPassing} of {a.membersTotal} passing
          </div>
        </div>
        <ScoreBar value={a.membersPassing / a.membersTotal} />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Max utilization
        </div>
        <div className="flex items-center gap-vs-2">
          <div className="font-mono text-[24px]">{formatPercent(a.maxUtilization)}</div>
          <span className="text-body-sm text-on-surface-variant">at {a.maxUtilizationElementId}</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-vs-3">
        <StatusRow
          label="Drift"
          value={a.maxDriftRatio}
          limit={a.allowableDrift}
          status={a.driftStatus}
        />
        <StatusRow
          label="Deflection"
          value={a.maxSlabDeflection}
          limit={a.allowableDeflection}
          status={a.deflectionStatus}
        />
      </div>
      {a.membersFailing.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
            Failing checks
          </div>
          <ul className="flex flex-col gap-vs-2">
            {a.membersFailing.map((m, i) => (
              <li
                key={i}
                className="flex items-center justify-between p-vs-2 bg-surface-container-low border-hairline rounded-sm text-body-sm"
              >
                <span className="inline-flex items-center gap-vs-2">
                  <AlertTriangle
                    className="w-3.5 h-3.5"
                    style={{ color: "var(--score-forbidden)" }}
                    strokeWidth={1.5}
                  />
                  <span className="font-mono text-[11px]">{m.elementId}</span>
                  <span className="text-on-surface-variant uppercase text-[10px] tracking-[0.08em]">
                    {m.check}
                  </span>
                </span>
                <span className="font-mono text-[12px]" style={{ color: "var(--score-forbidden)" }}>
                  {m.ratio.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatusRow({
  label,
  value,
  limit,
  status,
}: {
  label: string;
  value: string;
  limit: string;
  status: "pass" | "fail";
}) {
  const color =
    status === "pass" ? "var(--score-strong)" : "var(--score-forbidden)";
  return (
    <div className="flex flex-col gap-vs-1 p-vs-2 bg-surface-container-low border-hairline rounded-sm">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
        {label}
      </div>
      <div className="font-mono text-body-md">{value}</div>
      <div className="text-body-sm text-on-surface-variant">limit {limit}</div>
      <div className="inline-flex items-center gap-vs-1 text-body-sm mt-[2px]" style={{ color }}>
        {status === "pass" ? (
          <Check className="w-3 h-3" strokeWidth={1.5} />
        ) : (
          <AlertTriangle className="w-3 h-3" strokeWidth={1.5} />
        )}
        {status.toUpperCase()}
      </div>
    </div>
  );
}
