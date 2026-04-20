export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value));
  const color =
    pct >= 0.8 ? "var(--score-strong)" : pct >= 0.5 ? "var(--score-secondary)" : "var(--score-forbidden)";
  return (
    <span className="font-mono text-body-md" style={{ color }}>
      {pct.toFixed(2)}
    </span>
  );
}
