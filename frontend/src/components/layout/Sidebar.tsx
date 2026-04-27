"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";
import {
  ArrowDownToLine,
  BarChart3,
  Calculator,
  Clipboard,
  Clock3,
  Crosshair,
  FileDown,
  Grid3x3,
  Info,
  Layers,
  LayoutGrid,
  Lock,
  PanelLeftClose,
  PanelLeftOpen,
  PencilRuler,
  Ruler,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { toast } from "sonner";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";
import type { PhaseId } from "@/types/domain";
import { useSizerUiStore } from "@/stores/sizerUiStore";
import { downloadBlob, exportSizerPdf, getSelectedSizerResult } from "@/lib/sizer";

type NavItem = {
  label: string;
  icon: typeof LayoutGrid;
  subpath: string; // appended to /projects/[id]
  requiresPhase?: PhaseId;
  group: "views" | "tools";
  topLevel?: boolean; // /dashboard etc uses / instead of /projects/[id]/...
  action?: "assumptions" | "export";
};

const NAV: NavItem[] = [
  { label: "Dashboard", icon: LayoutGrid, subpath: "", topLevel: true, group: "views" },
  { label: "Input", icon: PencilRuler, subpath: "/input", group: "views" },
  { label: "Building graph", icon: Layers, subpath: "/building-graph", requiresPhase: 1, group: "views" },
  { label: "Structural zones", icon: Grid3x3, subpath: "/structural-zones", requiresPhase: 2, group: "views" },
  { label: "Support map", icon: Crosshair, subpath: "/support-map", requiresPhase: 2, group: "views" },
  { label: "Load paths", icon: ArrowDownToLine, subpath: "/load-paths", requiresPhase: 3, group: "views" },
  { label: "Analysis", icon: BarChart3, subpath: "/analysis", requiresPhase: 5, group: "views" },
  { label: "Design summary", icon: Clipboard, subpath: "/summary", group: "views" },
  { label: "Metadata", icon: Info, subpath: "/metadata", group: "tools" },
  { label: "History", icon: Clock3, subpath: "/history", group: "tools" },
  { label: "Settings", icon: Settings, subpath: "/settings", group: "tools" },
];

const SIZER_NAV: NavItem[] = [
  { label: "Overview", icon: BarChart3, subpath: "/sizer/overview", group: "views" },
  { label: "Members", icon: Calculator, subpath: "/sizer/members", group: "views" },
  { label: "Schemes", icon: Ruler, subpath: "/sizer/schemes", group: "views" },
  { label: "Calculations", icon: Clipboard, subpath: "/sizer/calculations", group: "views" },
  { label: "Export", icon: FileDown, subpath: "/sizer/overview", group: "views", action: "export" },
  { label: "Assumptions", icon: SlidersHorizontal, subpath: "/sizer/overview", group: "tools", action: "assumptions" },
  { label: "Settings", icon: Settings, subpath: "/sizer/settings", group: "tools" },
];

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const collapsed = useCanvasStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useCanvasStore((s) => s.toggleSidebar);
  const getAll = useProjectsStore((s) => s.getAll);
  const setAssumptionsOpen = useSizerUiStore((s) => s.setAssumptionsOpen);

  const projectMatch = pathname.match(/\/projects\/([^/]+)/);
  const projectId = projectMatch?.[1] ?? null;
  const project = useMemo(
    () => (projectId ? getAll().find((p) => p.id === projectId) ?? null : null),
    [projectId, getAll],
  );
  const nav = project?.projectType === "wood_framing_sizer" ? SIZER_NAV : NAV;

  function resolveHref(it: NavItem) {
    if (it.topLevel) return "/";
    if (!projectId) return "/"; // no project yet
    return `/projects/${projectId}${it.subpath}`;
  }

  function isActive(it: NavItem) {
    if (it.action) return false;
    if (it.topLevel) return pathname === "/" || pathname === "/projects";
    if (!projectId) return false;
    const href = `/projects/${projectId}${it.subpath}`;
    if (it.subpath === "") return pathname === `/projects/${projectId}`;
    return pathname.startsWith(href);
  }

  function isGated(it: NavItem) {
    if (!it.requiresPhase || !project) return false;
    return project.phaseStatus[it.requiresPhase] !== "complete";
  }

  async function handleAction(it: NavItem) {
    if (it.action === "assumptions") {
      setAssumptionsOpen(true);
      return;
    }
    if (it.action === "export") {
      const result = project ? getSelectedSizerResult(project) : null;
      if (!project || !result) {
        toast.error("No sizer result available to export.");
        return;
      }
      try {
        const blob = await exportSizerPdf(result);
        downloadBlob(blob, `${project.name.replace(/[^a-z0-9_-]+/gi, "-")}-calculations.pdf`);
        toast.success("Calculation package exported.");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Export failed.");
      }
      return;
    }
    router.push(resolveHref(it));
  }

  const viewItems = nav.filter((i) => i.group === "views");
  const toolItems = nav.filter((i) => i.group === "tools");

  return (
    <aside
      className="shrink-0 bg-surface-container-low border-r-hairline flex flex-col h-full"
      style={{ width: collapsed ? 56 : 240 }}
    >
      <div className={collapsed ? "px-vs-2 py-vs-3" : "px-vs-4 py-vs-3"}>
        {!collapsed && (
          <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
            Views
          </div>
        )}
        <nav className="flex flex-col gap-[2px]">
          {viewItems.map((it) => (
            <SidebarItem
              key={it.label}
              item={it}
              active={isActive(it)}
              gated={isGated(it)}
              collapsed={collapsed}
              onClick={() => {
                if (isGated(it)) return;
                void handleAction(it);
              }}
            />
          ))}
        </nav>
      </div>

      <div className="flex-1" />

      <div className={collapsed ? "px-vs-2 py-vs-3" : "px-vs-4 py-vs-3"}>
        {!collapsed && (
          <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
            Tools
          </div>
        )}
        <nav className="flex flex-col gap-[2px]">
          {toolItems.map((it) => (
            <SidebarItem
              key={it.label}
              item={it}
              active={isActive(it)}
              gated={false}
              collapsed={collapsed}
              onClick={() => void handleAction(it)}
            />
          ))}
        </nav>
        <button
          type="button"
          onClick={toggleSidebar}
          className="mt-vs-3 w-full inline-flex items-center gap-vs-2 h-8 px-vs-2 rounded-sm hover:bg-surface-container text-body-sm text-on-surface-variant tonal-hover"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? (
            <PanelLeftOpen className="w-4 h-4" strokeWidth={1.5} />
          ) : (
            <>
              <PanelLeftClose className="w-4 h-4" strokeWidth={1.5} />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

function SidebarItem({
  item,
  active,
  gated,
  collapsed,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  gated: boolean;
  collapsed: boolean;
  onClick: () => void;
}) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={gated}
      className={[
        "relative w-full inline-flex items-center gap-vs-3 h-8 rounded-sm tonal-hover",
        collapsed ? "px-vs-2 justify-center" : "px-vs-2",
        active
          ? "bg-surface-container text-on-surface"
          : gated
            ? "opacity-50 cursor-not-allowed text-on-surface-variant"
            : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
      ].join(" ")}
      title={
        collapsed
          ? gated
            ? `${item.label} — requires Phase ${item.requiresPhase} first`
            : item.label
          : gated
            ? `Requires Phase ${item.requiresPhase} to complete first`
            : undefined
      }
    >
      {active && !collapsed && (
        <span
          aria-hidden
          className="absolute left-0 top-1 bottom-1 w-[2px] rounded-full"
          style={{ background: "var(--on-surface)" }}
        />
      )}
      <Icon className="w-4 h-4 shrink-0" strokeWidth={1.5} />
      {!collapsed && (
        <span className="flex-1 text-left text-body-md truncate">{item.label}</span>
      )}
      {!collapsed && gated && <Lock className="w-3 h-3 text-on-surface-variant" />}
    </button>
  );
}
