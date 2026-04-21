"use client";

import { Lock, Play } from "lucide-react";
import type { PhaseId, ProjectV2 } from "@/types/domain";
import { useProjectsStore } from "@/stores/projectsStore";

type Props = {
  project: ProjectV2;
  requiredPhase: PhaseId;
  children: React.ReactNode;
};

const PHASE_LABEL: Record<PhaseId, string> = {
  1: "Phase 1 — Building graph",
  2: "Phase 2 — Structural zones",
  3: "Phase 3 — Load paths",
  4: "Phase 4 — Detailing",
  5: "Phase 5 — Analysis",
};

const PHASE_DESCRIPTION: Record<PhaseId, string> = {
  1: "Runs input parsing and element extraction.",
  2: "Derives structural zones and support candidates.",
  3: "Runs gravity + lateral load distribution.",
  4: "Phase 4 — member detailing and drawings.",
  5: "Member sizing + code compliance checks.",
};

export function PhaseGate({ project, requiredPhase, children }: Props) {
  const status = project.phaseStatus[requiredPhase];
  const runPhase2 = useProjectsStore((s) => s.runPhase2);
  const runPhase3 = useProjectsStore((s) => s.runPhase3);
  const runPhase5 = useProjectsStore((s) => s.runPhase5);

  if (status === "complete") return <>{children}</>;

  const isRunning = status === "running";

  function handleRun() {
    if (requiredPhase === 2) runPhase2(project.id);
    else if (requiredPhase === 3) runPhase3(project.id);
    else if (requiredPhase === 5) runPhase5(project.id);
  }

  return (
    <div className="flex-1 min-h-0 flex items-center justify-center bg-surface px-vs-6">
      <div className="max-w-[420px] w-full bg-surface-container-lowest border-hairline rounded-sm shadow-elev-1 p-vs-6 flex flex-col items-center text-center gap-vs-4">
        <div
          className="w-11 h-11 inline-flex items-center justify-center rounded-full"
          style={{ background: "var(--surface-container-low)" }}
        >
          <Lock className="w-4 h-4 text-on-surface-variant" strokeWidth={1.5} />
        </div>
        <div>
          <div className="text-title-md mb-vs-1">{PHASE_LABEL[requiredPhase]}</div>
          <p className="text-body-md text-on-surface-variant">
            {PHASE_DESCRIPTION[requiredPhase]} Run this phase to unlock the view.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={isRunning || requiredPhase === 4}
          className="inline-flex items-center gap-vs-2 h-9 px-vs-4 rounded-sm bg-on-surface text-on-primary text-body-md font-medium pressable disabled:opacity-50"
        >
          {isRunning ? (
            <>
              <span
                className="w-[6px] h-[6px] rounded-full pulse-dot"
                style={{ background: "var(--on-primary)" }}
              />
              Running…
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
              Run {PHASE_LABEL[requiredPhase]}
            </>
          )}
        </button>
        <div className="w-full text-left text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mt-vs-3 mb-vs-1">
          Phase status
        </div>
        <ul className="w-full flex flex-col gap-vs-1">
          {([1, 2, 3, 4, 5] as PhaseId[]).map((p) => {
            const s = project.phaseStatus[p];
            const dot =
              s === "complete"
                ? "var(--success)"
                : s === "running"
                  ? "var(--fn-blue)"
                  : s === "failed"
                    ? "var(--score-forbidden)"
                    : "var(--outline)";
            return (
              <li
                key={p}
                className="flex items-center gap-vs-2 text-body-sm"
              >
                <span
                  className="w-[6px] h-[6px] rounded-full"
                  style={{ background: dot }}
                />
                <span className="text-on-surface-variant flex-1">
                  {PHASE_LABEL[p]}
                </span>
                <span className="font-mono text-[11px] text-on-surface-variant">
                  {s.replace("_", " ")}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
