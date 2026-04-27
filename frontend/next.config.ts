import type { NextConfig } from "next";

const isProduction = process.env.NODE_ENV === "production";
const backend = process.env.BACKEND_PROXY_URL ?? (isProduction ? "" : "http://127.0.0.1:8000");
const sizerBackend =
  process.env.SIZER_BACKEND_PROXY_URL ?? (isProduction ? "" : "http://127.0.0.1:8001");

const nextConfig: NextConfig = {
  /** Optional same-origin proxy: use /api-proxy/api/v1/... -> FastAPI. */
  async rewrites() {
    const routes = [];
    if (backend) {
      routes.push(
        { source: "/api-proxy/health", destination: `${backend}/health` },
        { source: "/api-proxy/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      );
    }
    if (sizerBackend) {
      routes.push(
        { source: "/sizer-proxy/health", destination: `${sizerBackend}/health` },
        { source: "/sizer-proxy/api/v1/:path*", destination: `${sizerBackend}/api/v1/:path*` },
      );
    }
    return routes;
  },
};

export default nextConfig;
