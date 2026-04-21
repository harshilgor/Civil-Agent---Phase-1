import type { SupportClass, ZoneType } from "@/types/domain";

export const ZONE_FILL: Record<ZoneType, { stroke: string; fill: string; label: string }> = {
  core: { stroke: "var(--zone-core)", fill: "var(--zone-core)", label: "Core / service" },
  open_plate: {
    stroke: "var(--zone-open-plate)",
    fill: "var(--zone-open-plate)",
    label: "Open floor plate",
  },
  corridor: {
    stroke: "var(--zone-corridor)",
    fill: "var(--zone-corridor)",
    label: "Corridor band",
  },
  perimeter: {
    stroke: "var(--zone-perimeter)",
    fill: "var(--zone-perimeter)",
    label: "Perimeter",
  },
  transfer_risk: {
    stroke: "var(--zone-transfer-risk)",
    fill: "var(--zone-transfer-risk)",
    label: "Transfer risk",
  },
  high_clearance: {
    stroke: "var(--zone-high-clearance)",
    fill: "var(--zone-high-clearance)",
    label: "High clearance",
  },
  double_height: {
    stroke: "var(--zone-double-height)",
    fill: "var(--zone-double-height)",
    label: "Double height",
  },
};

export const SUPPORT_COLOR: Record<SupportClass, { dot: string; fill: string; text: string; label: string }> = {
  strong: {
    dot: "var(--score-strong)",
    fill: "var(--score-strong-container)",
    text: "var(--score-strong-on)",
    label: "Strong",
  },
  secondary: {
    dot: "var(--score-secondary)",
    fill: "var(--score-secondary-container)",
    text: "var(--score-secondary-on)",
    label: "Secondary",
  },
  weak: {
    dot: "var(--score-weak)",
    fill: "var(--score-weak-container)",
    text: "var(--score-weak-on)",
    label: "Weak",
  },
  forbidden: {
    dot: "var(--score-forbidden)",
    fill: "var(--score-forbidden-container)",
    text: "var(--score-forbidden-on)",
    label: "Forbidden",
  },
};

export function utilizationColor(ratio: number): string {
  if (ratio < 0.2) return "var(--util-0)";
  if (ratio < 0.5) return "var(--util-20)";
  if (ratio < 0.7) return "var(--util-50)";
  if (ratio < 0.85) return "var(--util-70)";
  if (ratio < 0.95) return "var(--util-85)";
  return "var(--util-95)";
}
