/**
 * Civil Agent FastAPI base URL.
 *
 * Backend default: http://localhost:8000 (see src/config.py api_port).
 * Set NEXT_PUBLIC_API_BASE_URL in .env.local to override.
 */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  return "http://localhost:8000";
}

/** GET /health — no /api/v1 prefix on the FastAPI app. */
export async function fetchCivilAgentHealth(): Promise<{
  ok: boolean;
  status?: string;
  error?: string;
}> {
  const base = getApiBaseUrl();
  try {
    const r = await fetch(`${base}/health`, { cache: "no-store" });
    if (!r.ok) return { ok: false, error: `HTTP ${r.status}` };
    const j = (await r.json()) as { status?: string };
    return { ok: true, status: j.status ?? "ok" };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/** Prefix for versioned REST routes: /api/v1/... */
export function apiV1Url(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}/api/v1${p}`;
}
