/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Task 1.6: a self-contained server (.next/standalone) that the web image copies; no npm install in the image.
  output: "standalone",
};

export default nextConfig;
