"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useCanvasStore } from "@/stores/canvasStore";
import { useProjectsStore } from "@/stores/projectsStore";

const VIEW_NAMES: Array<[RegExp, string]> = [
  [/^\/$/, "Projects dashboard"],
  [/\/projects\/[^/]+\/building-graph/, "Building graph"],
  [/\/projects\/[^/]+\/structural-zones/, "Structural zones"],
  [/\/projects\/[^/]+\/support-map/, "Support map"],
  [/\/projects\/[^/]+\/load-paths/, "Load paths"],
  [/\/projects\/[^/]+\/analysis/, "Analysis"],
  [/\/projects\/[^/]+\/summary/, "Design summary"],
  [/\/projects\/[^/]+\/compare/, "Comparison"],
  [/\/projects\/[^/]+\/input/, "Input"],
  [/\/projects\/[^/]+\/settings/, "Settings"],
  [/\/projects\/new/, "New project"],
  [/\/reports/, "Reports"],
];

export function StatusBar({
  cursor,
}: {
  cursor?: { x?: number; y?: number; z?: number } | null;
}) {
  const pathname = usePathname() ?? "/";
  const zoom = useCanvasStore((s) => s.zoom);
  const floor = useCanvasStore((s) => s.floor);
  const viewMode = useCanvasStore((s) => s.viewMode);
  const projectMatch = pathname.match(/\/projects\/([^/]+)/);
  const projectId = projectMatch?.[1] ?? null;
  const getAll = useProjectsStore((s) => s.getAll);
  const project = useMemo(
    () => (projectId ? getAll().find((p) => p.id === projectId) ?? null : null),
    [projectId, getAll],
  );

  const viewName =
    VIEW_NAMES.find(([re]) => re.test(pathname))?.[1] ?? "Civil Agent";

  const runningPhase = project
    ? (Object.entries(project.phaseStatus).find(([, v]) => v === "running")?.[0] as string | undefined)
    : undefined;

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!runningPhase) {
      setElapsed(0);
      return;
    }
    const start = Date.now();
    const t = setInterval(() => setElapsed(Date.now() - start), 100);
    return () => clearInterval(t);
  }, [runningPhase]);

  return (
    <footer
      className="h-7 w-full border-t-hairline bg-surface flex items-center justify-between px-vs-3 font-mono text-[11px] text-on-surface-variant select-none"
      style={{ minHeight: 28 }}
    >
      <div className="flex items-center gap-vs-4">
        <span>{viewName}</span>
        <span className="text-on-surface-variant">·</span>
        <span>
          {viewMode.toUpperCase()}{" "}
          <span className="text-on-surface/60">zoom {Math.round(zoom * 100)}%</span>
        </span>
        {project && (
          <>
            <span className="text-on-surface-variant">·</span>
            <span>Floor {floor === "all" ? "ALL" : floor}</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-vs-4">
        {cursor && (cursor.x != null || cursor.y != null) && (
          <span>
            X {(cursor.x ?? 0).toFixed(2)}m · Y {(cursor.y ?? 0).toFixed(2)}m
            {cursor.z != null && ` · Z ${cursor.z.toFixed(2)}m`}
          </span>
        )}
        {runningPhase ? (
          <span
            className="inline-flex items-center gap-vs-2"
            style={{ color: "var(--fn-blue)" }}
          >
            <span className="pulse-dot w-[6px] h-[6px] rounded-full" style={{ background: "var(--fn-blue)" }} />
            Phase {runningPhase} running · {(elapsed / 1000).toFixed(1)}s
          </span>
        ) : (
          <span className="inline-flex items-center gap-vs-2">
            <span className="w-[6px] h-[6px] rounded-full" style={{ background: "var(--success)" }} />
            Idle
          </span>
        )}
      </div>
    </footer>
  );
}
