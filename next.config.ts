import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  // Use standalone output for Amplify SSR hosting
  output: 'standalone',
  // Disable static page generation for pages that use client context
  experimental: {
    // @ts-ignore - Next.js 16 internal option
    isrFlushToDisk: false,
  },
};
export default nextConfig;
