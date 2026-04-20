export function ScoreBar({
  value,
  label,
  numeric = false,
}: {
  value: number;
  label?: string;
  numeric?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, value));
  const color =
    pct >= 0.8
      ? "var(--score-strong)"
      : pct >= 0.5
        ? "var(--score-secondary)"
        : "var(--score-forbidden)";
  return (
    <div className="flex items-center gap-vs-3 text-body-sm">
      {label && <span className="min-w-[140px] text-on-surface-variant">{label}</span>}
      <div
        className="relative flex-1 h-[6px] rounded-full overflow-hidden"
        style={{ background: "rgba(49,52,41,0.08)" }}
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${pct * 100}%`, background: color }}
        />
      </div>
      {numeric && (
        <span className="font-mono text-[13px] min-w-[40px] text-right">
          {pct.toFixed(2)}
        </span>
      )}
    </div>
  );
}
