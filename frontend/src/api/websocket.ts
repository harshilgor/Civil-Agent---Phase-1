export type JobProgressMessage = {
  job_id: string;
  status: string;
  progress_pct: number;
  current_stage: string | null;
};

const wsBase = () => {
  const env = import.meta.env.VITE_API_URL;
  if (env) return env.replace(/^http/, "ws");
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
};

export function connectJobSocket(
  jobId: string,
  onMessage: (m: JobProgressMessage) => void,
): WebSocket {
  const url = `${wsBase()}/ws/jobs/${jobId}`;
  const ws = new WebSocket(url);
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data as string) as JobProgressMessage);
    } catch {
      /* ignore */
    }
  };
  return ws;
}
