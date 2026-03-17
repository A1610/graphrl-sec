import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Use system TLS certs — fixes SSL errors on corporate/dev networks
  experimental: {
    turbopackUseSystemTlsCerts: true,
  },
  // Strict CSP-friendly image handling
  images: {
    domains: [],
  },
};

export default nextConfig;
