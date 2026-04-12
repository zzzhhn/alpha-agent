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

  // Output standalone for smaller deployments
  output: "standalone",
};

export default nextConfig;
