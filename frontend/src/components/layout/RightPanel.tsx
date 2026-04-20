"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { ReactNode, useMemo, useState } from "react";
import { useCanvasStore } from "@/stores/canvasStore";

export type RightPanelTab = { id: string; label: string; content: ReactNode };

export function RightPanel({
  tabs,
  defaultTab,
}: {
  tabs: RightPanelTab[];
  defaultTab?: string;
}) {
  const collapsed = useCanvasStore((s) => s.rightPanelCollapsed);
  const toggle = useCanvasStore((s) => s.toggleRightPanel);
  const [activeId, setActiveId] = useState(defaultTab ?? tabs[0]?.id);

  const active = useMemo(
    () => tabs.find((t) => t.id === activeId) ?? tabs[0],
    [tabs, activeId],
  );

  if (collapsed) {
    return (
      <div className="h-full border-l-hairline bg-surface-container-low flex items-start pt-vs-3">
        <button
          type="button"
          onClick={toggle}
          className="w-7 h-7 rounded-sm hover:bg-surface-container inline-flex items-center justify-center tonal-hover"
          aria-label="Expand right panel"
          title="Expand"
        >
          <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>
    );
  }

  return (
    <aside
      className="shrink-0 h-full border-l-hairline bg-surface-container-low flex flex-col"
      style={{ width: 320 }}
    >
      <div className="h-10 flex items-center justify-between px-vs-3 border-b-hairline">
        <div className="flex items-center gap-vs-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveId(t.id)}
              className={[
                "h-7 px-vs-2 rounded-sm text-body-sm font-medium tonal-hover",
                t.id === activeId
                  ? "bg-surface-container text-on-surface"
                  : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
              ].join(" ")}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={toggle}
          className="w-6 h-6 rounded-sm hover:bg-surface-container inline-flex items-center justify-center"
          aria-label="Collapse right panel"
          title="Collapse"
        >
          <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {active?.content ?? <div className="p-vs-4 text-body-sm text-on-surface-variant">Nothing selected.</div>}
      </div>
    </aside>
  );
}
