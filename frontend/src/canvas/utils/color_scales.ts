export function confidenceColor(conf: number): string {
  if (conf > 0.75) return "#3fb950";
  if (conf > 0.45) return "#d29922";
  return "#f85149";
}
