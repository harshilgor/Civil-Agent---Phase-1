"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { FileText } from "lucide-react";
import { useProjectsStore } from "@/stores/projectsStore";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatRel } from "@/lib/format";

export default function ReportsPage() {
  const projects = useSyncExternalStore(
    (l) => useProjectsStore.subscribe(l),
    () => useProjectsStore.getState().getAll(),
    () => [],
  );
  const exportable = projects.filter((p) => p.analysis !== null);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Reports"
        projectName="All projects"
        subtitle={`${exportable.length} projects ready for handoff`}
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        <div className="max-w-[960px] px-vs-6 py-vs-6">
          <ul className="flex flex-col divide-hairline border-hairline rounded-sm">
            {projects.map((p) => (
              <li
                key={p.id}
                className="flex items-center gap-vs-4 p-vs-3 hover:bg-surface-container-low"
              >
                <div
                  className="w-8 h-8 rounded-sm inline-flex items-center justify-center shrink-0"
                  style={{ background: "var(--surface-container-low)" }}
                >
                  <FileText className="w-4 h-4 text-on-surface-variant" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-body-md truncate">{p.name}</div>
                  <div className="text-body-sm text-on-surface-variant truncate">
                    {p.subtitle} · {formatRel(p.updatedAt)}
                  </div>
                </div>
                <StatusBadge status={p.status} />
                <Link
                  href={`/projects/${p.id}/summary`}
                  className="h-7 px-vs-3 rounded-sm border-hairline text-body-sm hover:bg-surface-container"
                >
                  Open handoff
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
