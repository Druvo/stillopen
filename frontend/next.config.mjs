const dev = process.env.NODE_ENV !== "production";
const django = process.env.DJANGO_ORIGIN || "http://127.0.0.1:8765";

/** @type {import('next').NextConfig} */
const config = {
  basePath: "/app",
  images: { unoptimized: true },
  reactStrictMode: true,
  // Production is a static export that Django serves; `next dev` proxies the API and sign-in to Django so the session cookie works.
  ...(dev
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${django}/api/:path*`, basePath: false },
            { source: "/accounts/:path*", destination: `${django}/accounts/:path*`, basePath: false },
            { source: "/jobs/:path*", destination: `${django}/jobs/:path*`, basePath: false },
            { source: "/dashboard/:path*", destination: `${django}/dashboard/:path*`, basePath: false },
          ];
        },
      }
    : { output: "export" }),
};

export default config;
