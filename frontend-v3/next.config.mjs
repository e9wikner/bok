/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    // When no explicit API URL is set, proxy /api/ and /health requests
    // to the backend. This makes the frontend work both with and without
    // an external reverse proxy (nginx).
    if (!apiUrl) {
      const backend = process.env.BACKEND_URL || 'http://localhost:8000';
      return [
        { source: '/api/:path*', destination: `${backend}/api/:path*` },
        { source: '/health', destination: `${backend}/health` },
      ];
    }
    return [];
  },
};

export default nextConfig;
