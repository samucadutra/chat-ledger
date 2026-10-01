import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The web app is self-contained in apps/web: trace from here, not the monorepo root.
  outputFileTracingRoot: process.cwd(),
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
