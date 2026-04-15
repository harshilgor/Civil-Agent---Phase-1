import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getJob, getResults } from "@/api/client";
import { useJobSubscription } from "@/hooks/useJob";
import { useJobStore } from "@/state/jobStore";

export function ProcessingPage() {
  const { jobId } = useParams();
  const nav = useNavigate();
  const job = useJobStore((s) => s.job);
  const setJob = useJobStore((s) => s.setJob);
  const setResults = useJobStore((s) => s.setResults);

  useJobSubscription(jobId);

  useEffect(() => {
    if (!jobId) return;
    void (async () => {
      try {
        setJob(await getJob(jobId));
      } catch {
        /* ignore */
      }
    })();
  }, [jobId, setJob]);

  useEffect(() => {
    if (job?.status !== "completed" || !jobId) return;
    void (async () => {
      try {
        setResults(await getResults(jobId));
        nav(`/viewer/${jobId}`);
      } catch {
        /* ignore */
      }
    })();
  }, [job?.status, jobId, nav, setResults]);

  return (
    <div style={{ padding: 24 }}>
      <h1>Processing</h1>
      {job ? (
        <pre>{JSON.stringify(job, null, 2)}</pre>
      ) : (
        <p>Loading job {jobId}…</p>
      )}
      <p>
        <Link to="/">Back</Link>
      </p>
    </div>
  );
}
