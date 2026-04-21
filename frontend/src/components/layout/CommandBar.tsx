"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Play, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useProjectsStore } from "@/stores/projectsStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { useCommandStore } from "@/stores/commandStore";
import { useHistoryStore } from "@/stores/historyStore";
import { COMMAND_SUGGESTIONS, parseCommand } from "@/lib/commandParser";

export function CommandBar() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [histIdx, setHistIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  const getAll = useProjectsStore((s) => s.getAll);
  const moveColumn = useProjectsStore((s) => s.moveColumn);
  const setWallType = useProjectsStore((s) => s.setWallType);
  const runPhase2 = useProjectsStore((s) => s.runPhase2);
  const runPhase3 = useProjectsStore((s) => s.runPhase3);
  const runPhase5 = useProjectsStore((s) => s.runPhase5);
  const setViewMode = useCanvasStore((s) => s.setViewMode);
  const setFloor = useCanvasStore((s) => s.setFloor);
  const setOverlayMode = useCanvasStore((s) => s.setOverlayMode);
  const resetView = useCanvasStore((s) => s.resetView);
  const zoomIn = useCanvasStore((s) => s.zoomIn);
  const zoomOut = useCanvasStore((s) => s.zoomOut);
  const addEntry = useCommandStore((s) => s.addEntry);
  const latest = useCommandStore((s) => s.latest);
  const clearLatest = useCommandStore((s) => s.clearLatest);
  const history = useCommandStore((s) => s.history);
  const addHistory = useHistoryStore((s) => s.add);

  const projectMatch = pathname.match(/\/projects\/([^/]+)/);
  const projectId = projectMatch?.[1] ?? null;
  const project = useMemo(
    () => (projectId ? getAll().find((p) => p.id === projectId) ?? null : null),
    [projectId, getAll],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape" && document.activeElement === inputRef.current) {
        inputRef.current?.blur();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (latest) {
      const t = setTimeout(() => clearLatest(), 5500);
      return () => clearTimeout(t);
    }
  }, [latest, clearLatest]);

  function runCommand(cmd: string) {
    const action = parseCommand(cmd, project);
    let kind: "info" | "success" | "warning" | "error" = "info";
    switch (action.kind) {
      case "navigate":
        router.push(action.route);
        kind = "success";
        break;
      case "canvas":
        if (action.action === "set_2d") setViewMode("2d");
        else if (action.action === "set_3d") setViewMode("3d");
        else if (action.action === "set_floor")
          setFloor(action.payload as number | "all");
        else if (action.action === "set_overlay")
          setOverlayMode(action.payload as "supports" | "zones" | "load_paths" | "utilization" | "none");
        else if (action.action === "fit") resetView();
        else if (action.action === "zoom_in") zoomIn();
        else if (action.action === "zoom_out") zoomOut();
        kind = "success";
        break;
      case "mutation":
        if (!project) {
          kind = "error";
          break;
        }
        if (action.action === "move_column") {
          const { columnId, x, y } = action.payload as {
            columnId: string;
            x: number;
            y: number;
          };
          const col = project.buildingGraph?.columnCandidates.find(
            (c) => c.id.toUpperCase().includes(columnId.toUpperCase()),
          );
          if (col) {
            moveColumn(project.id, col.id, [x, y]);
            addHistory(project.id, `Moved column ${col.gridIntersection} to (${x}, ${y})`);
            kind = "success";
          } else kind = "warning";
        }
        if (action.action === "change_wall_type") {
          const { wallId, type } = action.payload as { wallId: string; type: "structural" | "partition" | "shear" };
          setWallType(project.id, wallId, type);
          addHistory(project.id, `Changed wall ${wallId} to ${type}`);
          kind = "success";
        }
        break;
      case "run_phase":
        if (!project) {
          kind = "error";
          break;
        }
        if (action.phase === 2) runPhase2(project.id);
        if (action.phase === 3) runPhase3(project.id);
        if (action.phase === 5) runPhase5(project.id);
        addHistory(project.id, `Running Phase ${action.phase}…`, true);
        kind = "success";
        break;
      case "query":
        kind = "info";
        break;
      case "error":
        kind = "error";
        break;
      default:
        kind = "info";
    }
    addEntry({ command: cmd, response: action.message, kind });
    if (kind === "error") toast.error(action.message);
    else if (kind === "success") toast.success(action.message);
    else if (kind === "warning") toast.warning(action.message);
    else toast.message(action.message);
    setValue("");
    setHistIdx(-1);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && value.trim()) {
      e.preventDefault();
      runCommand(value.trim());
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length && histIdx < history.length - 1) {
        const next = histIdx + 1;
        setHistIdx(next);
        setValue(history[next].command);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (histIdx >= 0) {
        const next = histIdx - 1;
        setHistIdx(next);
        setValue(next >= 0 ? history[next].command : "");
      }
    }
  }

  return (
    <div
      className={[
        "w-full border-t-hairline bg-surface relative",
        "transition-[height] duration-150",
      ].join(" ")}
      style={{ height: focused ? 96 : 48 }}
    >
      {latest && (
        <div
          className="absolute left-vs-3 right-vs-3 -top-[52px] bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 px-vs-3 py-vs-2 text-body-md flex items-center gap-vs-2"
          role="status"
        >
          <Sparkles
            className="w-3.5 h-3.5 shrink-0"
            style={{
              color:
                latest.kind === "error"
                  ? "var(--score-forbidden)"
                  : latest.kind === "warning"
                    ? "var(--score-secondary)"
                    : latest.kind === "success"
                      ? "var(--score-strong)"
                      : "var(--fn-blue)",
            }}
          />
          <span className="flex-1">{latest.response}</span>
          <button
            type="button"
            className="text-body-sm text-on-surface-variant hover:underline"
            onClick={() => clearLatest()}
          >
            dismiss
          </button>
        </div>
      )}
      <div className="h-12 flex items-center px-vs-3 gap-vs-3">
        <Play
          className="w-3.5 h-3.5 text-on-surface-variant"
          strokeWidth={1.5}
          aria-hidden
        />
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setHistIdx(-1);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder={
            project
              ? "Type a command or ask a question…"
              : "Open a project to use the command bar…"
          }
          className="flex-1 bg-transparent outline-none text-body-lg font-mono placeholder:text-on-surface-variant/60"
        />
        <kbd className="font-mono text-[10px] text-on-surface-variant px-1.5 py-[2px] border-hairline rounded-sm">
          ⌘K
        </kbd>
        <button
          type="button"
          onClick={() => value.trim() && runCommand(value.trim())}
          className="inline-flex items-center gap-vs-1 h-7 px-vs-2 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium hover:opacity-90 pressable"
        >
          Run
          <CornerDownLeft className="w-3 h-3" strokeWidth={1.5} />
        </button>
      </div>
      {focused && (
        <div className="px-vs-3 pb-vs-2 flex items-center gap-vs-2 overflow-x-auto">
          {COMMAND_SUGGESTIONS.map((s) => (
            <button
              type="button"
              key={s}
              onMouseDown={(e) => {
                e.preventDefault();
                setValue(s);
                runCommand(s);
              }}
              className="shrink-0 inline-flex items-center h-7 px-vs-2 rounded-sm bg-surface-container-low border-hairline text-body-sm text-on-surface-variant hover:bg-surface-container hover:text-on-surface tonal-hover"
            >
              <Sparkles className="w-3 h-3 mr-vs-1" strokeWidth={1.5} />
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
