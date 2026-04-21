"use client";

import { use, useSyncExternalStore } from "react";
import { notFound } from "next/navigation";
import { Clock3, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { useProjectsStore } from "@/stores/projectsStore";
import { useHistoryStore } from "@/stores/historyStore";
import { formatRel } from "@/lib/format";

export default function HistoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const project = useProjectsStore((s) => s.getProject(id));
  const entries = useSyncExternalStore(
    (l) => useHistoryStore.subscribe(l),
    () => useHistoryStore.getState().entries[id] ?? EMPTY,
    () => EMPTY,
  );
  const clear = useHistoryStore((s) => s.clear);

  if (!project) notFound();

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="History"
        projectName={project.name}
        subtitle={`${entries.length} entr${entries.length === 1 ? "y" : "ies"}`}
        actions={
          entries.length > 0 ? (
            <button
              type="button"
              onClick={() => {
                clear(project.id);
                toast.success("History cleared.");
              }}
              className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              <Trash2 className="w-3 h-3" strokeWidth={1.5} />
              Clear
            </button>
          ) : null
        }
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        <div className="max-w-[720px] px-vs-6 py-vs-6">
          {entries.length === 0 ? (
            <EmptyState />
          ) : (
            <ol className="flex flex-col divide-hairline border-hairline rounded-sm">
              {entries.map((e) => (
                <li
                  key={e.id}
                  className="flex items-start gap-vs-3 p-vs-3 hover:bg-surface-container-low"
                >
                  <div
                    className="w-7 h-7 rounded-sm inline-flex items-center justify-center shrink-0"
                    style={{ background: "var(--surface-container-low)" }}
                  >
                    {e.system ? (
                      <Sparkles
                        className="w-3 h-3"
                        style={{ color: "var(--fn-blue)" }}
                        strokeWidth={1.5}
                      />
                    ) : (
                      <Clock3 className="w-3 h-3 text-on-surface-variant" strokeWidth={1.5} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-body-md">{e.label}</div>
                    <div className="text-body-sm text-on-surface-variant font-mono text-[11px]">
                      {formatRel(e.timestamp)}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

const EMPTY: never[] = [];

function EmptyState() {
  return (
    <div className="py-vs-12 text-center text-body-md text-on-surface-variant">
      No commands or mutations recorded yet. Try moving a column, running a phase, or using the command bar.
    </div>
  );
}
