import type { NextConfig } from "next";

// The browser always calls same-origin /api/v1/*; Next proxies it to the
// FastAPI backend, so the backend needs no CORS setup. Override with
// BACKEND_URL when the API runs elsewhere (e.g. another laptop on the LAN).
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Keep the development badge out of screen recordings and demos.
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
