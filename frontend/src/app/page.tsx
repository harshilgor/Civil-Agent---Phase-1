"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";
import { Plus, MoreHorizontal, Building2, Copy, Trash2, ExternalLink, Download } from "lucide-react";
import { MetricCard } from "@/components/shared/MetricCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { SourceBadge } from "@/components/shared/SourceBadge";
import { ConfidenceBadge } from "@/components/shared/ConfidenceBadge";
import { FilterPill } from "@/components/shared/FilterPill";
import { useProjectsStore } from "@/stores/projectsStore";
import type { ProjectStatus, ProjectV2 } from "@/types/domain";
import { formatRel } from "@/lib/format";
import { toast } from "sonner";

type StatusFilter = "all" | ProjectStatus;
type SortBy = "recent" | "name" | "confidence";

function useProjects(): ProjectV2[] {
  const getAll = useProjectsStore((s) => s.getAll);
  const subscribe = useProjectsStore.subscribe;
  // useSyncExternalStore → stable snapshots for SSR/client hydration
  const snapshot = useSyncExternalStore(
    (l) => subscribe(l),
    () => JSON.stringify(getAll().map((p) => p.id + p.updatedAt)),
    () => "ssr",
  );
  return useMemo(() => getAll(), [snapshot, getAll]);
}

export default function Dashboard() {
  const router = useRouter();
  const projects = useProjects();
  const deleteProject = useProjectsStore((s) => s.deleteProject);
  const duplicateProject = useProjectsStore((s) => s.duplicateProject);

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("recent");

  const counts = useMemo(() => {
    const by = (s: ProjectStatus) => projects.filter((p) => p.status === s).length;
    return {
      total: projects.length,
      complete: by("COMPLETE"),
      processing: by("PROCESSING"),
      needsReview: by("NEEDS_REVIEW"),
    };
  }, [projects]);

  const filtered = useMemo(() => {
    let list = projects;
    if (statusFilter !== "all") list = list.filter((p) => p.status === statusFilter);
    if (sortBy === "name") list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    else if (sortBy === "confidence")
      list = [...list].sort((a, b) => b.phase2Confidence - a.phase2Confidence);
    else list = [...list].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
    return list;
  }, [projects, statusFilter, sortBy]);

  return (
    <div className="flex-1 min-h-0 overflow-auto">
      <div className="mx-auto max-w-[1440px] px-vs-8 py-vs-6 flex flex-col gap-vs-6">
        {/* Action bar */}
        <div className="flex items-end justify-between gap-vs-4 flex-wrap">
          <div className="flex flex-col gap-vs-1">
            <h1 className="font-headline text-headline-lg font-medium leading-none">
              Projects
            </h1>
            <p className="text-body-md text-on-surface-variant">
              {counts.total} {counts.total === 1 ? "project" : "projects"} ·{" "}
              {counts.processing} in progress
            </p>
          </div>
          <div className="flex items-center gap-vs-2">
            <FilterPill<StatusFilter>
              label="Filter"
              value={statusFilter}
              options={[
                { value: "all", label: "All" },
                { value: "COMPLETE", label: "Complete" },
                { value: "PROCESSING", label: "Processing" },
                { value: "NEEDS_REVIEW", label: "Needs review" },
                { value: "FAILED", label: "Failed" },
              ]}
              onChange={setStatusFilter}
            />
            <FilterPill<SortBy>
              label="Sort"
              value={sortBy}
              options={[
                { value: "recent", label: "Recent" },
                { value: "name", label: "Name" },
                { value: "confidence", label: "Confidence" },
              ]}
              onChange={setSortBy}
            />
            <button
              type="button"
              onClick={() => router.push("/projects/new")}
              className="h-8 inline-flex items-center gap-vs-2 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-md font-medium hover:opacity-90 pressable"
            >
              <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
              New project
            </button>
          </div>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-vs-3">
          <MetricCard
            label="Total"
            value={counts.total}
            sublabel="projects"
            active={statusFilter === "all"}
            onClick={() => setStatusFilter("all")}
          />
          <MetricCard
            label="Complete"
            value={counts.complete}
            sublabel="projects"
            active={statusFilter === "COMPLETE"}
            onClick={() => setStatusFilter("COMPLETE")}
          />
          <MetricCard
            label="In progress"
            value={counts.processing}
            sublabel="projects"
            active={statusFilter === "PROCESSING"}
            onClick={() => setStatusFilter("PROCESSING")}
          />
          <MetricCard
            label="Needs review"
            value={counts.needsReview}
            sublabel="projects"
            active={statusFilter === "NEEDS_REVIEW"}
            onClick={() => setStatusFilter("NEEDS_REVIEW")}
          />
        </div>

        {/* Project table */}
        {filtered.length === 0 ? (
          <div className="border-hairline rounded-sm bg-surface-container-lowest p-vs-12 flex flex-col items-center justify-center gap-vs-4 text-center">
            <Building2 className="w-10 h-10 text-on-surface-variant/50" strokeWidth={1.25} />
            <div className="flex flex-col gap-vs-1">
              <div className="text-title-md font-medium">
                {statusFilter === "all" ? "No projects yet" : `No ${statusFilter.toLowerCase().replace("_", " ")} projects`}
              </div>
              <div className="text-body-sm text-on-surface-variant">
                {statusFilter === "all"
                  ? "Create your first structural design to get started."
                  : "Clear the filter or create a new project."}
              </div>
            </div>
            {statusFilter === "all" ? (
              <Link
                href="/projects/new"
                className="h-8 inline-flex items-center gap-vs-2 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-md font-medium hover:opacity-90 pressable"
              >
                <Plus className="w-3.5 h-3.5" />
                Create your first project
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => setStatusFilter("all")}
                className="h-8 px-vs-3 rounded-sm border-hairline text-body-md hover:bg-surface-container-low"
              >
                Show all
              </button>
            )}
          </div>
        ) : (
          <div className="border-hairline rounded-sm bg-surface-container-lowest overflow-hidden">
            <div className="grid grid-cols-[minmax(240px,1fr)_110px_140px_120px_130px_130px_60px] px-vs-4 py-vs-3 border-b-hairline bg-surface-container-low text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
              <div>Project</div>
              <div>Source</div>
              <div>Phase 1</div>
              <div>Phase 2</div>
              <div>Status</div>
              <div>Last modified</div>
              <div></div>
            </div>
            <ul className="divide-y divide-[rgba(49,52,41,0.08)]">
              {filtered.map((p) => (
                <ProjectRow
                  key={p.id}
                  project={p}
                  onOpen={() => router.push(`/projects/${p.id}/building-graph`)}
                  onDuplicate={() => {
                    const newId = duplicateProject(p.id);
                    if (newId) toast.success(`Duplicated "${p.name}"`);
                  }}
                  onDelete={() => {
                    deleteProject(p.id);
                    toast.success(`Deleted "${p.name}"`);
                  }}
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function ProjectRow({
  project,
  onOpen,
  onDuplicate,
  onDelete,
}: {
  project: ProjectV2;
  onOpen: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const rel = formatRel(project.updatedAt);

  return (
    <li
      className="grid grid-cols-[minmax(240px,1fr)_110px_140px_120px_130px_130px_60px] px-vs-4 py-vs-3 items-center hover:bg-surface-container-low tonal-hover cursor-pointer"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
    >
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-vs-2 text-body-md font-medium truncate">
          {project.name}
        </div>
        <div className="text-body-sm text-on-surface-variant truncate">
          {project.buildingType} · {project.subtitle}
        </div>
      </div>
      <div>
        <SourceBadge source={project.source} />
      </div>
      <div>
        <div className="flex items-center gap-vs-2">
          <div
            className="h-[4px] w-16 rounded-full overflow-hidden"
            style={{ background: "rgba(49,52,41,0.08)" }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.round(project.phase1Completeness * 100)}%`,
                background:
                  project.phase1Completeness >= 0.8
                    ? "var(--score-strong)"
                    : "var(--score-secondary)",
              }}
            />
          </div>
          <span className="font-mono text-[12px] text-on-surface-variant">
            {Math.round(project.phase1Completeness * 100)}%
          </span>
        </div>
      </div>
      <div>
        {project.phase2Confidence > 0 ? (
          <ConfidenceBadge value={project.phase2Confidence} />
        ) : (
          <span className="text-body-sm text-on-surface-variant">—</span>
        )}
      </div>
      <div>
        <StatusBadge status={project.status} />
      </div>
      <div className="text-body-sm text-on-surface-variant">
        {rel}
      </div>
      <div
        className="relative flex justify-end"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          className="w-6 h-6 rounded-sm hover:bg-surface-container inline-flex items-center justify-center"
          aria-label="Project actions"
        >
          <MoreHorizontal className="w-4 h-4" />
        </button>
        {menuOpen && (
          <div
            className="absolute right-0 top-full mt-1 w-44 bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 z-30 overflow-hidden"
            onMouseLeave={() => setMenuOpen(false)}
          >
            <MenuItem icon={ExternalLink} onClick={onOpen} label="Open" />
            <MenuItem icon={Copy} onClick={onDuplicate} label="Duplicate" />
            <MenuItem
              icon={Download}
              onClick={() => toast.info("Export coming in Reports view")}
              label="Export"
            />
            <MenuItem
              icon={Trash2}
              onClick={onDelete}
              label="Delete"
              danger
            />
          </div>
        )}
      </div>
    </li>
  );
}

function MenuItem({
  icon: Icon,
  onClick,
  label,
  danger,
}: {
  icon: typeof Copy;
  onClick: () => void;
  label: string;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "w-full text-left px-vs-3 py-vs-2 text-body-sm flex items-center gap-vs-2 hover:bg-surface-container-low",
        danger ? "text-error" : "text-on-surface",
      ].join(" ")}
    >
      <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
      {label}
    </button>
  );
}
