import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /* Penpot DWO/Core semantic aliases (canonical) */
        dwo: {
          canvas: "var(--dwo-color-bg-canvas)",
          surface: "var(--dwo-color-bg-surface)",
          panel: "var(--dwo-color-bg-surface)",
          subtle: "var(--dwo-color-bg-subtle)",
          border: "var(--dwo-color-border-default)",
          edge: "var(--dwo-color-border-default)",
          primary: "var(--dwo-color-text-primary)",
          muted: "var(--dwo-color-text-muted)",
          faint: "var(--dwo-color-text-faint)",
          accent: "var(--dwo-color-accent-blue)",
          success: "var(--dwo-color-state-green)",
          warning: "var(--dwo-color-state-amber)",
          error: "var(--dwo-color-state-red)",
          info: "var(--dwo-color-state-purple)",
        },
        /* Legacy Observatory palette (backward compat, aliased to canonical) */
        surface: "var(--color-surface)",
        panel: "var(--color-panel)",
        edge: "var(--color-edge)",
        muted: "var(--color-text-muted)",
        accent: "var(--color-accent)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      spacing: {
        1: "var(--space-1)",
        2: "var(--space-2)",
        3: "var(--space-3)",
        4: "var(--space-4)",
        5: "var(--space-5)",
        6: "var(--space-6)",
      },
    },
  },
  plugins: [],
};

export default config;
