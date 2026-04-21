"use client";

import { AlertTriangle, Check, Info } from "lucide-react";
import type { ProjectV2 } from "@/types/domain";
import { formatPercent } from "@/lib/format";
import { ScoreBar } from "@/components/shared/ScoreBar";

export function AssumptionsPanel({ project }: { project: ProjectV2 }) {
  const graph = project.buildingGraph;
  if (!graph) {
    return (
      <div className="p-vs-4 text-body-sm text-on-surface-variant">
        No building graph generated yet.
      </div>
    );
  }
  return (
    <div className="p-vs-4 flex flex-col gap-vs-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Phase 1 confidence
        </div>
        <div className="flex items-end justify-between gap-vs-3 mb-vs-2">
          <div className="font-mono text-[28px] leading-none">
            {formatPercent(graph.completeness)}
          </div>
          <div className="text-body-sm text-on-surface-variant">
            overall completeness
          </div>
        </div>
        <ScoreBar value={graph.completeness} />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Section scores
        </div>
        <div className="flex flex-col gap-vs-2">
          {Object.entries(graph.sectionScores).map(([k, v]) => (
            <ScoreBar key={k} label={capitalize(k.replace("_", " "))} value={v} />
          ))}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Assumptions
        </div>
        <ul className="flex flex-col gap-vs-2">
          {graph.assumptions.map((a, i) => (
            <li key={i} className="flex items-start gap-vs-2 text-body-sm">
              <Info
                className="w-3.5 h-3.5 shrink-0 mt-[2px]"
                style={{ color: "var(--fn-blue)" }}
                strokeWidth={1.5}
              />
              <span>{a}</span>
            </li>
          ))}
        </ul>
      </div>
      {graph.warnings.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
            Warnings
          </div>
          <ul className="flex flex-col gap-vs-2">
            {graph.warnings.map((w, i) => (
              <li key={i} className="flex items-start gap-vs-2 text-body-sm">
                <AlertTriangle
                  className="w-3.5 h-3.5 shrink-0 mt-[2px]"
                  style={{ color: "var(--score-secondary)" }}
                  strokeWidth={1.5}
                />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {graph.missingFields.length === 0 && (
        <div className="flex items-center gap-vs-2 text-body-sm" style={{ color: "var(--score-strong)" }}>
          <Check className="w-3.5 h-3.5" strokeWidth={1.5} />
          All expected fields present.
        </div>
      )}
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
