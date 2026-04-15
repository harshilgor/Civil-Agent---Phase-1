import { useEffect } from "react";
import { getJob } from "@/api/client";
import { connectJobSocket } from "@/api/websocket";
import { useJobStore } from "@/state/jobStore";

export function useJobSubscription(jobId: string | undefined, pollMs = 2000) {
  const setJob = useJobStore((s) => s.setJob);

  useEffect(() => {
    if (!jobId) return;
    const ws = connectJobSocket(jobId, (m) => {
      setJob({
        id: m.job_id,
        status: m.status as "queued" | "running" | "completed" | "failed",
        progress_pct: m.progress_pct,
        current_stage: m.current_stage,
      });
    });
    const t = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setJob(j);
      } catch {
        /* ignore */
      }
    }, pollMs);
    return () => {
      ws.close();
      clearInterval(t);
    };
  }, [jobId, pollMs, setJob]);
}
