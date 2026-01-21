/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow WebSocket connections in dev
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: "*",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
