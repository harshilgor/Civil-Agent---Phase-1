"use client";

import { ReactNode } from "react";

export function ViewHeader({
  title,
  projectName,
  subtitle,
  badges,
  actions,
}: {
  title: string;
  projectName: string;
  subtitle?: string;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="h-12 shrink-0 border-b-hairline bg-surface flex items-center px-vs-4 gap-vs-4">
      <div className="flex items-center gap-vs-3 flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant shrink-0">
          {title}
        </div>
        <span className="text-on-surface-variant">·</span>
        <div className="text-body-md truncate">{projectName}</div>
        {subtitle && (
          <>
            <span className="text-on-surface-variant">·</span>
            <div className="text-body-sm text-on-surface-variant truncate">
              {subtitle}
            </div>
          </>
        )}
        {badges && <div className="flex items-center gap-vs-2 ml-vs-2">{badges}</div>}
      </div>
      {actions && <div className="flex items-center gap-vs-2 shrink-0">{actions}</div>}
    </header>
  );
}
