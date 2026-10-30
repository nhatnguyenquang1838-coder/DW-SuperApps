/**
 * Gate local fixture-preview routes behind an explicit source selection.
 * Production can never serve the development fixture pack, even if the
 * environment variable is accidentally carried into the deployment.
 */
export function isLocalFixturePreview(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  return env.NODE_ENV !== "production" && env.OBSERVATORY_DATA_SOURCE === "fixture";
}
