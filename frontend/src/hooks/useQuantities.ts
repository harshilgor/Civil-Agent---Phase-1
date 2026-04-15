import { useEffect } from "react";
import type { PipelineResults } from "@/api/types";
import { useQuantityStore } from "@/state/quantityStore";

function computeStub(results: PipelineResults | null) {
  if (!results?.rooms?.length) {
    return { areas: [], wallLengthM: 0 };
  }
  const total = results.rooms.reduce((a, r) => a + r.polygon.length, 0) || 1;
  return {
    areas: results.rooms.map((r) => ({
      roomId: r.id,
      label: r.label,
      areaM2: 0,
      pctTotal: (100 * r.polygon.length) / total,
    })),
    wallLengthM: 0,
  };
}

export function useQuantities(results: PipelineResults | null) {
  const setQuantities = useQuantityStore((s) => s.setQuantities);
  useEffect(() => {
    setQuantities(computeStub(results));
  }, [results, setQuantities]);
}
