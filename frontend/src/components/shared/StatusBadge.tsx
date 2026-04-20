import type { ProjectStatus } from "@/types/domain";

const STYLES: Record<ProjectStatus, { bg: string; dot: string; text: string; label: string }> = {
  COMPLETE: {
    bg: "var(--score-strong-container)",
    dot: "var(--score-strong)",
    text: "var(--score-strong-on)",
    label: "Complete",
  },
  PROCESSING: {
    bg: "var(--fn-blue-container)",
    dot: "var(--fn-blue)",
    text: "#042c53",
    label: "Processing",
  },
  NEEDS_REVIEW: {
    bg: "var(--score-secondary-container)",
    dot: "var(--score-secondary)",
    text: "var(--score-secondary-on)",
    label: "Needs review",
  },
  FAILED: {
    bg: "var(--score-forbidden-container)",
    dot: "var(--score-forbidden)",
    text: "var(--score-forbidden-on)",
    label: "Failed",
  },
};

export function StatusBadge({
  status,
  compact = false,
}: {
  status: ProjectStatus;
  compact?: boolean;
}) {
  const s = STYLES[status];
  return (
    <span
      className="inline-flex items-center gap-vs-2 rounded-sm px-vs-2 py-[2px] text-body-sm font-medium"
      style={{ background: s.bg, color: s.text }}
    >
      <span
        aria-hidden
        className={`inline-block w-[6px] h-[6px] rounded-full ${
          status === "PROCESSING" ? "pulse-dot" : ""
        }`}
        style={{ background: s.dot }}
      />
      {!compact && (
        <span className="tracking-[0.04em] text-[11px] uppercase">{s.label}</span>
      )}
    </span>
  );
}
