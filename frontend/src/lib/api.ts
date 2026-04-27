/**
 * Civil Agent FastAPI base URL.
 *
 * Backend default: http://localhost:8000 (see src/config.py api_port).
 * Set NEXT_PUBLIC_API_BASE_URL in .env.local to override.
 */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    if (isLocalHostname(window.location.hostname)) {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    return "";
  }
  return "http://localhost:8000";
}

export function getSizerApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SIZER_API_BASE_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    if (isLocalHostname(window.location.hostname)) {
      return `${window.location.protocol}//${window.location.hostname}:8001`;
    }
    return "";
  }
  return "http://localhost:8001";
}

/** GET /health — no /api/v1 prefix on the FastAPI app. */
export async function fetchCivilAgentHealth(): Promise<{
  ok: boolean;
  status?: string;
  error?: string;
}> {
  const base = getApiBaseUrl();
  try {
    const r = await fetch(base ? `${base}/health` : "/api-proxy/health", { cache: "no-store" });
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

export async function fetchSizerHealth(): Promise<{
  ok: boolean;
  status?: string;
  error?: string;
}> {
  const base = getSizerApiBaseUrl();
  try {
    const r = await fetch(base ? `${base}/health` : "/sizer-proxy/health", { cache: "no-store" });
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
  const base = getApiBaseUrl();
  if (!base) return `/api-proxy/api/v1${p}`;
  return `${base}/api/v1${p}`;
}

export function sizerApiV1Url(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = getSizerApiBaseUrl();
  if (!base) return `/sizer-proxy/api/v1${p}`;
  return `${base}/api/v1${p}`;
}

function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}
