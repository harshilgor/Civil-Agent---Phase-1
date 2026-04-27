import type { NextConfig } from "next";

const backend = process.env.BACKEND_PROXY_URL ?? "http://127.0.0.1:8000";
const sizerBackend = process.env.SIZER_BACKEND_PROXY_URL ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  /** Optional same-origin proxy: use /api-proxy/api/v1/... → FastAPI (avoids CORS during dev). */
  async rewrites() {
    return [
      { source: "/api-proxy/health", destination: `${backend}/health` },
      { source: "/api-proxy/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      { source: "/sizer-proxy/health", destination: `${sizerBackend}/health` },
      { source: "/sizer-proxy/api/v1/:path*", destination: `${sizerBackend}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
