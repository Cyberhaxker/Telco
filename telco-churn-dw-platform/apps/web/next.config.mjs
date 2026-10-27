import { createHash } from "node:crypto";
import withSerwistInit from "@serwist/next";

// Every page of the static export is precached so the whole app opens offline.
const ROUTES = [
  "/", "/login", "/auth/callback", "/dashboard", "/olap", "/predictions", "/data-entry",
  "/uploads", "/sync", "/metadata", "/models", "/admin", "/offline",
];
const revision = process.env.BUILD_REVISION ?? createHash("sha256").update(String(Date.now())).digest("hex").slice(0, 12);

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  additionalPrecacheEntries: [
    ...ROUTES.map((url) => ({ url, revision })),
    { url: "/manifest.webmanifest", revision },
  ],
  disable: process.env.NODE_ENV === "development",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained server for the Docker image (login routes need the Next.js server).
  output: "standalone",
  serverExternalPackages: ["bcryptjs", "mysql2"], // traced into node_modules so the seed script can import them
  reactStrictMode: true,
  compress: false, // keeps the SSE stream (/api/v1/analytics/stream) unbuffered
  async rewrites() {
    // In Docker the gateway is reachable as apisix:9080; the browser only talks to this origin.
    const gateway = process.env.GATEWAY_UPSTREAM;
    return gateway ? [{ source: "/api/v1/:path*", destination: `http://${gateway}/api/v1/:path*` }] : [];
  },
  poweredByHeader: false,
  images: { unoptimized: true },
  trailingSlash: false,
};

export default withSerwist(nextConfig);
