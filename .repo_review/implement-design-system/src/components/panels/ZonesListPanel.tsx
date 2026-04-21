"use client";

import type { ProjectV2 } from "@/types/domain";
import { ZONE_FILL } from "@/lib/colors";
import { useSelectionStore } from "@/stores/selectionStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { formatM2 } from "@/lib/format";

export function ZonesListPanel({ project }: { project: ProjectV2 }) {
  const structural = project.structuralGraph;
  const floor = useCanvasStore((s) => s.floor);
  const sel = useSelectionStore((s) => s.selection);
  const select = useSelectionStore((s) => s.select);

  if (!structural) {
    return (
      <div className="p-vs-4 text-body-sm text-on-surface-variant">
        Structural graph not generated.
      </div>
    );
  }
  const zones = structural.zones.filter(
    (z) => floor === "all" || z.floor === floor,
  );

  return (
    <div className="p-vs-4 flex flex-col gap-vs-3">
      <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
        Zones ({zones.length})
      </div>
      <ul className="flex flex-col divide-hairline">
        {zones.map((z) => {
          const info = ZONE_FILL[z.type];
          const active = sel.kind === "zone" && sel.id === z.id;
          return (
            <li key={z.id}>
              <button
                type="button"
                onClick={() => select("zone", z.id)}
                className={[
                  "w-full py-vs-2 px-vs-2 -mx-vs-2 text-left flex items-start gap-vs-2 rounded-sm tonal-hover",
                  active ? "bg-surface-container" : "hover:bg-surface-container",
                ].join(" ")}
              >
                <span
                  className="w-2.5 h-2.5 rounded-[2px] mt-[4px] shrink-0"
                  style={{ background: info.fill, opacity: 0.8 }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-body-md">{info.label}</div>
                  <div className="text-body-sm text-on-surface-variant flex items-center gap-vs-2">
                    <span>Floor {z.floor}</span>
                    <span>·</span>
                    <span className="font-mono">{formatM2(z.areaM2)}</span>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="border-t-hairline pt-vs-3">
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-2">
          Building regularity
        </div>
        <div className="flex flex-col gap-vs-1 text-body-sm">
          <Row k="Type" v={capitalize(structural.buildingRegularity)} />
          <Row k="Framing direction" v={structural.framingDirection.toUpperCase()} />
          <Row
            k="Typical span"
            v={`${(structural.typicalSpanMm / 1000).toFixed(1)} m`}
          />
          <Row
            k="Span regularity"
            v={`${Math.round(structural.spanRegularity * 100)}%`}
          />
          <Row
            k="Vertical alignment"
            v={`${Math.round(structural.verticalAlignmentQuality * 100)}%`}
          />
          <Row
            k="Transfer floors"
            v={
              structural.transferFloors.length
                ? structural.transferFloors.join(", ")
                : "None"
            }
          />
        </div>
      </div>
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-vs-2">
      <span className="text-on-surface-variant">{k}</span>
      <span className="font-mono text-[11px]">{v}</span>
    </div>
  );
}
