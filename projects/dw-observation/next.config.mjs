/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // M1 is a read-only historical UI; no server actions, no output export needed.
  // Keep framework defaults. Observatory is a self-contained app under projects/dw-observation.
};

export default nextConfig;
