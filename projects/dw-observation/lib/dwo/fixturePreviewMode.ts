/**
 * Gate local fixture-preview routes behind an explicit source selection.
 * Production can never serve the development fixture pack, even if the
 * environment variable is accidentally carried into the deployment.
 *
 * Delegates to the centralized datasource config (lib/dwo/dataSourceConfig)
 * so the preview gate and any runtime datasource switch share one decision.
 */
import { getDataSource } from "./dataSourceConfig";

export function isLocalFixturePreview(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  // getDataSource() reflects the module-cached config (set at load or via
  // setDataSource/initDataSource). Also check the raw env var so callers that
  // mutate process.env after module load (e.g. tests) still take effect.
  return (
    (getDataSource() === "fixture" || env.OBSERVATORY_DATA_SOURCE === "fixture") &&
    env.NODE_ENV !== "production"
  );
}
