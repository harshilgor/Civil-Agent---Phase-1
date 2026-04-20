import { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  sublabel,
  active = false,
  onClick,
  accent,
}: {
  label: string;
  value: string | number;
  sublabel?: string;
  active?: boolean;
  onClick?: () => void;
  accent?: ReactNode;
}) {
  const Tag = onClick ? ("button" as const) : ("div" as const);
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={[
        "group text-left border-hairline rounded-sm px-vs-4 py-vs-3 flex flex-col gap-vs-2 tonal-hover",
        active
          ? "bg-surface-container-high"
          : "bg-surface-container-low hover:bg-surface-container",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          {label}
        </span>
        {accent}
      </div>
      <div className="font-headline font-medium text-headline-md leading-none">
        {value}
      </div>
      {sublabel && (
        <div className="text-body-sm text-on-surface-variant">{sublabel}</div>
      )}
    </Tag>
  );
}
