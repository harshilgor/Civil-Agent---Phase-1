"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  ChevronDown,
  Compass,
  FileText,
  LayoutDashboard,
  Search,
  User,
} from "lucide-react";
import { useProjectsStore } from "@/stores/projectsStore";

type ProjectMatch = ReturnType<typeof useProjectsStore.getState>["userProjects"][number];

function useCurrentProject() {
  const pathname = usePathname();
  const getAll = useProjectsStore((s) => s.getAll);
  return useMemo(() => {
    const m = pathname?.match(/\/projects\/([^/]+)/);
    if (!m) return null;
    return getAll().find((p) => p.id === m[1]) ?? null;
  }, [pathname, getAll]);
}

export function TopBar() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const project = useCurrentProject();
  const renameProject = useProjectsStore((s) => s.renameProject);
  const getAll = useProjectsStore((s) => s.getAll);

  const [renaming, setRenaming] = useState(false);
  const [rename, setRename] = useState("");
  const [search, setSearch] = useState("");
  const [searchFocus, setSearchFocus] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!searchFocus) return;
    function onClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node))
        setSearchFocus(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [searchFocus]);

  const tabs: Array<{
    label: string;
    match: (p: string) => boolean;
    href: string;
    icon: typeof LayoutDashboard;
  }> = [
    {
      label: "Projects",
      match: (p) => p === "/" || p.startsWith("/projects") && !p.match(/\/projects\/[^/]+/)?.length ||
        p.startsWith("/projects") && !(p.includes("/projects/") && p.split("/projects/")[1]?.length),
      href: "/",
      icon: LayoutDashboard,
    },
    {
      label: "Design",
      match: (p) => /\/projects\/[^/]+/.test(p) && !p.endsWith("/summary") && !p.endsWith("/reports"),
      href: project ? `/projects/${project.id}/building-graph` : "/",
      icon: Compass,
    },
    {
      label: "Reports",
      match: (p) => p.startsWith("/reports") || /\/projects\/[^/]+\/summary/.test(p),
      href: project ? `/projects/${project.id}/summary` : "/reports",
      icon: FileText,
    },
  ];

  const isProjectsTab = pathname === "/" || (pathname.startsWith("/projects") && !/\/projects\/[^/]+/.test(pathname));

  const searchResults = useMemo(() => {
    if (!search.trim()) return [];
    const q = search.toLowerCase();
    return getAll()
      .filter((p) =>
        [p.name, p.buildingType, p.subtitle, p.id]
          .join(" ")
          .toLowerCase()
          .includes(q),
      )
      .slice(0, 6);
  }, [search, getAll]);

  function commitRename() {
    if (!project) return;
    const trimmed = rename.trim();
    if (trimmed && trimmed !== project.name) renameProject(project.id, trimmed);
    setRenaming(false);
  }

  return (
    <header
      className="h-12 w-full bg-surface border-b-hairline flex items-center pl-vs-4 pr-vs-3 gap-vs-6 select-none"
      style={{ minHeight: 48 }}
    >
      <Link href="/" className="flex items-center gap-vs-2 pressable">
        <div
          className="w-6 h-6 rounded-sm flex items-center justify-center"
          style={{
            background: "var(--on-surface)",
            color: "var(--on-primary)",
          }}
          aria-hidden
        >
          <Compass className="w-3.5 h-3.5" strokeWidth={1.5} />
        </div>
        <span className="font-headline text-title-sm font-medium tracking-tight">
          CIVIL AGENT
        </span>
      </Link>

      {project && (
        <div className="flex items-center gap-vs-2 pl-vs-3 ml-vs-3 border-l-hairline">
          <span className="text-body-sm text-on-surface-variant">/</span>
          {renaming ? (
            <input
              autoFocus
              value={rename}
              onChange={(e) => setRename(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitRename();
                if (e.key === "Escape") setRenaming(false);
              }}
              className="bg-surface-container-low text-title-sm font-medium px-vs-2 py-[2px] rounded-sm border-hairline outline-none focus:border-secondary"
            />
          ) : (
            <button
              type="button"
              className="text-title-sm font-medium hover:underline underline-offset-2"
              onClick={() => {
                setRename(project.name);
                setRenaming(true);
              }}
              title="Click to rename project"
            >
              {project.name}
            </button>
          )}
        </div>
      )}

      <nav className="flex-1 flex items-center justify-center gap-vs-1" aria-label="Primary">
        {tabs.map((t) => {
          const active =
            (t.label === "Projects" && isProjectsTab) ||
            (t.label !== "Projects" && t.match(pathname));
          const Icon = t.icon;
          const disabled = t.label !== "Projects" && !project;
          return (
            <button
              key={t.label}
              type="button"
              disabled={disabled}
              onClick={() => !disabled && router.push(t.href)}
              className={[
                "inline-flex items-center gap-vs-2 h-8 px-vs-3 rounded-sm text-body-md font-medium tonal-hover",
                active
                  ? "bg-surface-container-low text-on-surface"
                  : "text-on-surface-variant hover:bg-surface-container-low",
                disabled ? "opacity-40 cursor-not-allowed" : "",
              ].join(" ")}
            >
              <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
              {t.label}
            </button>
          );
        })}
      </nav>

      <div ref={searchRef} className="relative w-[280px]">
        <div className="flex items-center gap-vs-2 h-8 px-vs-3 border-hairline rounded-sm bg-surface-container-lowest">
          <Search className="w-3.5 h-3.5 text-on-surface-variant" strokeWidth={1.5} />
          <input
            placeholder="Search projects, elements, constraints..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onFocus={() => setSearchFocus(true)}
            className="flex-1 bg-transparent outline-none text-body-md placeholder:text-on-surface-variant"
          />
          <kbd className="font-mono text-[10px] text-on-surface-variant px-1 border-hairline rounded-sm">
            ⌘K
          </kbd>
        </div>
        {searchFocus && searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 z-50 overflow-hidden">
            {searchResults.map((p) => (
              <button
                type="button"
                key={p.id}
                onClick={() => {
                  router.push(`/projects/${p.id}/building-graph`);
                  setSearchFocus(false);
                  setSearch("");
                }}
                className="w-full text-left px-vs-3 py-vs-2 hover:bg-surface-container-low flex items-center justify-between gap-vs-3"
              >
                <div className="flex flex-col">
                  <span className="text-body-md font-medium">{p.name}</span>
                  <span className="text-body-sm text-on-surface-variant">
                    {p.buildingType}
                  </span>
                </div>
                <span className="text-body-sm font-mono text-on-surface-variant">
                  {p.id}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-vs-1">
        <NotificationButton />
        <UserMenu />
      </div>
    </header>
  );
}

function NotificationButton() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-8 h-8 rounded-sm hover:bg-surface-container-low inline-flex items-center justify-center tonal-hover relative"
        aria-label="Notifications"
      >
        <Bell className="w-4 h-4" strokeWidth={1.5} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-[320px] bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 z-50">
          <div className="px-vs-3 py-vs-2 border-b-hairline text-[11px] uppercase tracking-[0.08em] text-on-surface-variant">
            Notifications
          </div>
          <div className="px-vs-3 py-vs-4 text-body-sm text-on-surface-variant text-center">
            No new notifications.
          </div>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-vs-1 h-8 px-vs-2 rounded-sm hover:bg-surface-container-low tonal-hover"
      >
        <span
          className="w-6 h-6 rounded-full inline-flex items-center justify-center"
          style={{ background: "var(--secondary)", color: "var(--on-secondary)" }}
        >
          <User className="w-3.5 h-3.5" strokeWidth={1.5} />
        </span>
        <ChevronDown className="w-3 h-3 text-on-surface-variant" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-[220px] bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 z-50 overflow-hidden">
          <div className="px-vs-3 py-vs-2 border-b-hairline">
            <div className="text-body-md font-medium">Engineer</div>
            <div className="text-body-sm text-on-surface-variant">
              engineer@civilagent.io
            </div>
          </div>
          {["Account", "Settings", "Keyboard shortcuts", "Logout"].map((l) => (
            <button
              key={l}
              type="button"
              className="w-full text-left px-vs-3 py-vs-2 text-body-md hover:bg-surface-container-low"
            >
              {l}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
