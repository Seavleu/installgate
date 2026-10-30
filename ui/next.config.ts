import type { NextConfig } from "next";

// The Cloudflare Workers build (OpenNext) produces its own bundle and rejects
// a standalone server build, so standalone is on for every other target:
// `pnpm dev`, `pnpm build` and the Docker image compose uses.
const forCloudflare = process.env.CF_WORKER === "1";

const nextConfig: NextConfig = {
  ...(forCloudflare ? {} : { output: "standalone" as const }),
  devIndicators: false,
};

export default nextConfig;
