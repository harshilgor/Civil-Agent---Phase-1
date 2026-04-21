import type { NextConfig } from "next";

const backend = process.env.BACKEND_PROXY_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /** Optional same-origin proxy: use /api-proxy/api/v1/... → FastAPI (avoids CORS during dev). */
  async rewrites() {
    return [
      { source: "/api-proxy/health", destination: `${backend}/health` },
      { source: "/api-proxy/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
