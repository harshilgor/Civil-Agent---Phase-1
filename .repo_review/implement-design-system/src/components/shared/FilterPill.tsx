"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function FilterPill<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (v: T) => void;
}) {
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

  const current = options.find((o) => o.value === value);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="h-8 px-vs-3 inline-flex items-center gap-vs-2 rounded-sm border-hairline bg-surface-container-lowest text-body-sm hover:bg-surface-container-low tonal-hover"
      >
        <span className="text-on-surface-variant">{label}:</span>
        <span className="font-medium">{current?.label}</span>
        <ChevronDown className="w-3 h-3 text-on-surface-variant" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 min-w-[200px] bg-surface-container-lowest border-hairline rounded-sm shadow-elev-2 z-40 overflow-hidden">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={[
                "w-full text-left px-vs-3 py-vs-2 text-body-sm hover:bg-surface-container-low",
                o.value === value ? "bg-surface-container-low font-medium" : "",
              ].join(" ")}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
