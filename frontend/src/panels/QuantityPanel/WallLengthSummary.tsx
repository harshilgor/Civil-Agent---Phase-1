import { useQuantityStore } from "@/state/quantityStore";

export function WallLengthSummary() {
  const wall = useQuantityStore((s) => s.quantities?.wallLengthM ?? 0);
  return <div>Wall length: {wall.toFixed(2)} m (stub)</div>;
}
