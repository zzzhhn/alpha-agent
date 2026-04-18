/** @type {import('next').NextConfig} */
const nextConfig = {
  // Rewrite API calls to the AutoDL FastAPI backend
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:6008";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${apiUrl}/ws/:path*`,
      },
    ];
  },

  // Route / to the primary research dashboard. Config-level redirect emits
  // a proper HTTP 308 with Location header (vs. App-Router redirect() which
  // in some deploy modes returned a 307 without Location and landed clients
  // on the error boundary).
  async redirects() {
    return [
      {
        source: "/",
        destination: "/data",
        permanent: true,
      },
    ];
  },

  // Output standalone for smaller deployments
  output: "standalone",
};

export default nextConfig;
