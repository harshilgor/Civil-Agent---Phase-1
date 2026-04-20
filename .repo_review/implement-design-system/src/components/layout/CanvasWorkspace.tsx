"use client";

import { ReactNode } from "react";
import { RightPanel, RightPanelTab } from "./RightPanel";
import { CommandBar } from "./CommandBar";

export function CanvasWorkspace({
  canvas,
  rightPanelTabs,
  hideCommandBar = false,
  hideRightPanel = false,
}: {
  canvas: ReactNode;
  rightPanelTabs?: RightPanelTab[];
  hideCommandBar?: boolean;
  hideRightPanel?: boolean;
}) {
  return (
    <div className="flex-1 min-h-0 flex">
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 min-h-0 relative">{canvas}</div>
        {!hideCommandBar && <CommandBar />}
      </div>
      {!hideRightPanel && rightPanelTabs && rightPanelTabs.length > 0 && (
        <RightPanel tabs={rightPanelTabs} />
      )}
    </div>
  );
}
