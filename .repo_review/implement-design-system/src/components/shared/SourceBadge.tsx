import type { InputSource } from "@/types/domain";

const STYLES: Record<InputSource, { bg: string; fg: string }> = {
  STRUCTURED: { bg: "var(--primary-container)", fg: "var(--on-primary-container)" },
  IFC: { bg: "var(--fn-blue-container)", fg: "#042c53" },
  DXF: { bg: "var(--fn-purple-container)", fg: "#3a206d" },
  IMAGE: { bg: "var(--fn-pink-container)", fg: "#5a1f44" },
};

export function SourceBadge({ source }: { source: InputSource }) {
  const s = STYLES[source];
  return (
    <span
      className="inline-flex items-center rounded-sm px-vs-2 py-[2px] text-[10px] font-medium tracking-[0.08em] uppercase"
      style={{ background: s.bg, color: s.fg }}
    >
      {source}
    </span>
  );
}
