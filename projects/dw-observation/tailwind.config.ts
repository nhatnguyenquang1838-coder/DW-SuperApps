import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Observatory read-only palette
        surface: "#0b0f17",
        panel: "#121826",
        edge: "#1f2a3a",
        muted: "#8b98ad",
        accent: "#5b9dff",
      },
    },
  },
  plugins: [],
};

export default config;
