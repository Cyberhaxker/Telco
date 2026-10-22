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
  output: "export",
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  trailingSlash: false,
};

export default withSerwist(nextConfig);
