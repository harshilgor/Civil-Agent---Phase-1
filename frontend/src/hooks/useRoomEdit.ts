import { patchRoom } from "@/api/client";
import type { PipelineResults } from "@/api/types";
import { useJobStore } from "@/state/jobStore";

export function useRoomEdit(jobId: string | undefined) {
  const setResults = useJobStore((s) => s.setResults);

  return async (roomId: string, body: Record<string, unknown>) => {
    if (!jobId) return;
    const updated = (await patchRoom(jobId, roomId, body)) as PipelineResults;
    setResults(updated);
  };
}
