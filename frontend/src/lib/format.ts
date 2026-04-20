export function formatMm(mm: number, precision = 0): string {
  return mm.toLocaleString("en-US", { maximumFractionDigits: precision }) + " mm";
}

export function formatM(mm: number, precision = 1): string {
  return (mm / 1000).toLocaleString("en-US", {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }) + " m";
}

export function formatM2(m2: number): string {
  return m2.toLocaleString("en-US", { maximumFractionDigits: 1 }) + " m²";
}

export function formatRel(timestamp: string): string {
  const d = new Date(timestamp);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 4) return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
  return d.toLocaleDateString();
}

export function formatPercent(v: number, precision = 0): string {
  return (v * 100).toFixed(precision) + "%";
}

export function formatKn(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " kN";
}
