/** @type {import('next').NextConfig} */
const nextConfig = {
  // Bake the deploy's commit SHA into the client bundle so VersionWatcher can
  // compare the loaded version against the live one (/api/version) and prompt
  // a refresh after a new deploy. VERCEL_GIT_COMMIT_SHA is a build-time system
  // env on Vercel; "dev" locally (both sides "dev" → never prompts).
  env: {
    NEXT_PUBLIC_BUILD_ID: process.env.VERCEL_GIT_COMMIT_SHA || "dev",
  },

  // Rewrite API calls to the AutoDL FastAPI backend
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:6008";
    return [
      {
        // Exclude /api/auth/* and /api/fe/* from this rewrite. /api/auth/* is
        // NextAuth's own routes; /api/fe/* is frontend-native API (e.g.
        // /api/fe/version for the deploy-version check). Both are handled by
        // Next route handlers under src/app/api/. All other /api/* paths proxy
        // to the FastAPI backend as before.
        source: "/api/:path((?!auth/|fe/).*)",
        destination: `${apiUrl}/api/:path`,
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
