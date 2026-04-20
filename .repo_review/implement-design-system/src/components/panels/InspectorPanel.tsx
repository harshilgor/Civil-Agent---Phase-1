"use client";

import { useMemo } from "react";
import type { ProjectV2 } from "@/types/domain";
import { useSelectionStore } from "@/stores/selectionStore";
import { SUPPORT_COLOR, ZONE_FILL } from "@/lib/colors";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { formatM, formatM2, formatMm, formatPercent } from "@/lib/format";

type Props = {
  project: ProjectV2;
};

export function InspectorPanel({ project }: Props) {
  const selection = useSelectionStore((s) => s.selection);
  const clear = useSelectionStore((s) => s.clear);
  const graph = project.buildingGraph;
  const structural = project.structuralGraph;

  const content = useMemo(() => {
    if (!selection.id || !graph) return null;
    switch (selection.kind) {
      case "wall": {
        const w = graph.walls.find((w) => w.id === selection.id);
        if (!w) return null;
        const dx = w.end[0] - w.start[0];
        const dy = w.end[1] - w.start[1];
        const lengthMm = Math.hypot(dx, dy);
        return (
          <div className="flex flex-col gap-vs-3">
            <InspectorHeader title={`Wall ${w.id}`} subtitle={w.type.toUpperCase()} />
            <KV label="Type" value={w.type} />
            <KV label="Material" value={w.material} />
            <KV label="Length" value={formatM(lengthMm, 2)} />
            <KV label="Thickness" value={formatMm(w.thicknessMm)} />
            <KV label="Height" value={formatMm(w.heightMm)} />
            <KV label="Stories" value={w.stories.join(", ")} />
            <KV label="Confidence" value={formatPercent(w.confidence)} />
          </div>
        );
      }
      case "room": {
        const r = graph.rooms.find((r) => r.id === selection.id);
        if (!r) return null;
        return (
          <div className="flex flex-col gap-vs-3">
            <InspectorHeader title={r.label} subtitle={r.type.toUpperCase()} />
            <KV label="Area" value={formatM2(r.areaM2)} />
            <KV label="Floor" value={`${r.floor}`} />
            <KV label="Type" value={r.type} />
            <KV label="ID" value={r.id} mono />
          </div>
        );
      }
      case "column": {
        const c = graph.columnCandidates.find((c) => c.id === selection.id);
        if (!c) return null;
        const pal = SUPPORT_COLOR[c.classification];
        return (
          <div className="flex flex-col gap-vs-3">
            <InspectorHeader
              title={`Column ${c.gridIntersection}`}
              subtitle={`Floor ${c.floor} · Support candidate`}
            />
            <div
              className="inline-flex items-center gap-vs-2 text-body-sm px-vs-2 h-6 rounded-sm self-start"
              style={{ background: pal.fill, color: pal.text }}
            >
              <span
                className="w-[6px] h-[6px] rounded-full"
                style={{ background: pal.dot }}
              />
              {pal.label} · {c.score.toFixed(2)}
            </div>
            <KV
              label="Position"
              value={`${(c.position[0] / 1000).toFixed(2)}, ${(c.position[1] / 1000).toFixed(2)} m`}
              mono
            />
            <KV label="Tributary" value={formatM2(c.tributaryAreaM2)} />
            <KV label="Stacked" value={c.stackedAcrossAllFloors ? "Yes" : "No"} />
            <div className="border-t-hairline pt-vs-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
                Score decomposition
              </div>
              <div className="flex flex-col gap-vs-2">
                <ScoreBar label="Grid alignment" value={c.decomposition.gridAlignment} />
                <ScoreBar label="Wall support" value={c.decomposition.wallSupport} />
                <ScoreBar label="Zone compatibility" value={c.decomposition.zoneCompatibility} />
                <ScoreBar label="Perimeter factor" value={c.decomposition.perimeterFactor} />
                <ScoreBar label="Tributary area" value={c.decomposition.tributaryArea} />
              </div>
            </div>
          </div>
        );
      }
      case "zone": {
        const z = structural?.zones.find((z) => z.id === selection.id);
        if (!z) return null;
        const fill = ZONE_FILL[z.type];
        return (
          <div className="flex flex-col gap-vs-3">
            <InspectorHeader title={fill.label} subtitle={`Zone ${z.id}`} />
            <div
              className="inline-flex items-center gap-vs-2 text-body-sm px-vs-2 h-6 rounded-sm self-start"
              style={{ background: fill.fill, color: fill.stroke, opacity: 0.85 }}
            >
              {z.type.replace("_", " ")}
            </div>
            <KV label="Floor" value={`${z.floor}`} />
            <KV label="Area" value={formatM2(z.areaM2)} />
            <KV label="Perimeter" value={`${z.perimeterM.toFixed(1)} m`} />
            {z.notes.length > 0 && (
              <div className="pt-vs-2 border-t-hairline">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
                  Notes
                </div>
                <ul className="text-body-sm text-on-surface-variant flex flex-col gap-vs-1 list-disc pl-vs-4">
                  {z.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      }
      default:
        return null;
    }
  }, [selection, graph, structural]);

  if (!content) {
    return (
      <div className="p-vs-4 flex flex-col gap-vs-3 text-body-sm text-on-surface-variant">
        <div className="text-[10px] uppercase tracking-[0.12em]">Inspector</div>
        <div>Select an element to inspect its properties.</div>
        <div className="pt-vs-3 border-t-hairline">
          <div className="text-[10px] uppercase tracking-[0.12em] mb-vs-2">
            Graph summary
          </div>
          {graph && (
            <dl className="flex flex-col gap-vs-1 font-mono text-[11px]">
              <Row label="Walls" value={`${graph.walls.length}`} />
              <Row label="Rooms" value={`${graph.rooms.length}`} />
              <Row label="Cores" value={`${graph.cores.length}`} />
              <Row label="Columns / floor" value={`${graph.columnCandidates.filter((c) => c.floor === 1).length}`} />
              <Row label="Stories" value={`${graph.stories}`} />
              <Row label="Footprint" value={`${formatM(graph.lengthMm, 1)} × ${formatM(graph.widthMm, 1)}`} />
            </dl>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-vs-4 flex flex-col gap-vs-3">
      {content}
      <button
        type="button"
        onClick={clear}
        className="mt-vs-2 self-start text-body-sm text-on-surface-variant hover:text-on-surface underline"
      >
        Clear selection
      </button>
    </div>
  );
}

function InspectorHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div>
      <div className="text-title-sm mb-vs-1">{title}</div>
      {subtitle && (
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          {subtitle}
        </div>
      )}
    </div>
  );
}

function KV({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-vs-3 text-body-sm">
      <span className="w-[110px] text-on-surface-variant shrink-0">{label}</span>
      <span className={mono ? "font-mono text-[11px]" : ""}>{value}</span>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-vs-2">
      <span className="text-on-surface-variant">{label}</span>
      <span className="text-on-surface">{value}</span>
    </div>
  );
}
