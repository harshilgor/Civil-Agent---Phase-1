import { confidenceColor } from "@/canvas/utils/color_scales";

export function ConfidenceBadge({ value }: { value: number }) {
  return (
    <span style={{ background: confidenceColor(value), padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
      {(value * 100).toFixed(0)}%
    </span>
  );
}
