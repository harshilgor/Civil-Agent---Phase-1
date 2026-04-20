"use client";

import { useMemo, useState } from "react";
import type { ProjectV2, SupportClass } from "@/types/domain";
import { SUPPORT_COLOR } from "@/lib/colors";
import { useSelectionStore } from "@/stores/selectionStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { formatM2 } from "@/lib/format";

const CLASS_ORDER: SupportClass[] = ["strong", "secondary", "weak", "forbidden"];

export function SupportsPanel({
  project,
  filter,
  onFilterChange,
}: {
  project: ProjectV2;
  filter: Record<SupportClass, boolean>;
  onFilterChange: (next: Record<SupportClass, boolean>) => void;
}) {
  const floor = useCanvasStore((s) => s.floor);
  const sel = useSelectionStore((s) => s.selection);
  const select = useSelectionStore((s) => s.select);
  const graph = project.buildingGraph;
  const [sort, setSort] = useState<"score" | "tributary" | "grid">("score");

  const candidates = useMemo(() => {
    if (!graph) return [];
    const list = graph.columnCandidates.filter((c) =>
      floor === "all" ? c.floor === 1 : c.floor === floor,
    );
    const sorted = [...list];
    if (sort === "score") sorted.sort((a, b) => b.score - a.score);
    else if (sort === "tributary")
      sorted.sort((a, b) => b.tributaryAreaM2 - a.tributaryAreaM2);
    else sorted.sort((a, b) => a.gridIntersection.localeCompare(b.gridIntersection));
    return sorted;
  }, [graph, floor, sort]);

  if (!graph) {
    return (
      <div className="p-vs-4 text-body-sm text-on-surface-variant">
        No graph generated.
      </div>
    );
  }

  const counts: Record<SupportClass, number> = {
    strong: 0,
    secondary: 0,
    weak: 0,
    forbidden: 0,
  };
  candidates.forEach((c) => counts[c.classification]++);

  function toggleClass(k: SupportClass) {
    onFilterChange({ ...filter, [k]: !filter[k] });
  }

  return (
    <div className="p-vs-4 flex flex-col gap-vs-3">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
        Support candidates
      </div>

      <div className="flex flex-col gap-vs-1">
        {CLASS_ORDER.map((k) => {
          const pal = SUPPORT_COLOR[k];
          return (
            <label
              key={k}
              className="flex items-center gap-vs-2 cursor-pointer text-body-sm tonal-hover px-vs-1 h-7 rounded-sm hover:bg-surface-container"
            >
              <input
                type="checkbox"
                checked={filter[k]}
                onChange={() => toggleClass(k)}
                className="accent-[var(--secondary)]"
              />
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ background: pal.dot }}
              />
              <span className="flex-1">{pal.label}</span>
              <span className="font-mono text-[11px] text-on-surface-variant">
                {counts[k]}
              </span>
            </label>
          );
        })}
      </div>

      <div className="flex items-center gap-vs-2 pt-vs-2 border-t-hairline">
        <span className="text-body-sm text-on-surface-variant">Sort</span>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "score" | "tributary" | "grid")}
          className="h-7 text-body-sm px-vs-2 border-hairline rounded-sm bg-surface outline-none"
        >
          <option value="score">Score (high → low)</option>
          <option value="tributary">Tributary area</option>
          <option value="grid">Grid label</option>
        </select>
      </div>

      <ul className="flex flex-col max-h-[360px] overflow-y-auto divide-hairline">
        {candidates
          .filter((c) => filter[c.classification])
          .map((c) => {
            const pal = SUPPORT_COLOR[c.classification];
            const active = sel.kind === "column" && sel.id === c.id;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => select("column", c.id)}
                  className={[
                    "w-full py-vs-2 text-left flex items-center gap-vs-2",
                    active ? "bg-surface-container" : "hover:bg-surface-container",
                  ].join(" ")}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0 ml-vs-1"
                    style={{ background: pal.dot }}
                  />
                  <span className="font-mono text-[13px] w-14">
                    {c.gridIntersection}
                  </span>
                  <span className="flex-1 text-body-sm text-on-surface-variant">
                    {formatM2(c.tributaryAreaM2)} trib
                  </span>
                  <span className="font-mono text-[12px] text-on-surface-variant mr-vs-2">
                    {c.score.toFixed(2)}
                  </span>
                </button>
              </li>
            );
          })}
      </ul>
    </div>
  );
}
