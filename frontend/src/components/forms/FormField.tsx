"use client";

import { ReactNode } from "react";

export function FormField({
  label,
  children,
  hint,
  flashed,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  flashed?: boolean;
}) {
  return (
    <label className={"flex flex-col gap-vs-1 " + (flashed ? "field-flash" : "")}>
      <span className="text-body-sm font-medium text-on-surface-variant">
        {label}
      </span>
      {children}
      {hint && <span className="text-body-sm text-on-surface-variant/80">{hint}</span>}
      <style jsx>{`
        .field-flash :global(input),
        .field-flash :global(select),
        .field-flash :global(textarea) {
          animation: flash 0.9s ease-out;
        }
        @keyframes flash {
          0% {
            background-color: var(--score-strong-container);
          }
          100% {
            background-color: var(--surface-container-lowest);
          }
        }
      `}</style>
    </label>
  );
}

export function FormSection({
  title,
  index,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className="border-hairline rounded-sm bg-surface-container-lowest">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-vs-4 py-vs-3 tonal-hover hover:bg-surface-container-low"
      >
        <div className="flex items-center gap-vs-3">
          <span
            className="w-5 h-5 rounded-full inline-flex items-center justify-center font-mono text-[11px]"
            style={{ background: "var(--surface-container-high)" }}
          >
            {String(index).padStart(2, "0")}
          </span>
          <span className="font-headline text-title-md font-medium">{title}</span>
        </div>
        <span className="text-body-sm text-on-surface-variant">
          {expanded ? "−" : "+"}
        </span>
      </button>
      {expanded && (
        <div className="border-t-hairline px-vs-4 py-vs-4 grid gap-vs-4">
          {children}
        </div>
      )}
    </section>
  );
}
