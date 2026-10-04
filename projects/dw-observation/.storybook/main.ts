import path from "node:path";
import type { StorybookConfig } from "@storybook/react-webpack5";

const config: StorybookConfig = {
  stories: ["../stories/**/*.mdx", "../stories/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: ["@storybook/addon-a11y", "@storybook/addon-docs"],
  framework: "@storybook/react-webpack5",
  docs: { autodocs: "tag" },
  webpackFinal: async (webpackConfig) => {
    // Configure ts-loader for .tsx/.ts files with JSX support
    if (webpackConfig.module?.rules) {
      // Find and replace the TypeScript rule
      webpackConfig.module.rules = webpackConfig.module.rules.map((rule: any) => {
        if (rule.test && rule.test.toString().includes("ts")) {
          return {
            test: /\.tsx?$/,
            loader: "ts-loader",
            options: {
              transpileOnly: true,
              compilerOptions: { jsx: "react-jsx" },
            },
            exclude: /node_modules/,
          };
        }
        return rule;
      });
    }
    // Add path alias for @
    if (webpackConfig.resolve?.alias) {
      webpackConfig.resolve.alias = {
        ...webpackConfig.resolve.alias,
        "@": path.resolve(__dirname, ".."),
      };
    }
    return webpackConfig;
  },
};
export default config;