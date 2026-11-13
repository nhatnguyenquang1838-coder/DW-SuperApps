/**
 * Datasource config — runtime switchable source selection for DWO.
 *
 * Controls whether the observability surfaces read from the real backend
 * (Supabase / task gateway) or from in-repo fixtures. Intended for local
 * development and review only — fixture mode is NEVER allowed in production.
 *
 * The config is process-scoped: setDataSource() mutates the current process.
 * It is NOT persisted across server restarts and never written to disk.
 *
 * Design decisions:
 *  1. A single source of truth for the datasource decision. Every surface that
 *     previously read OBSERVATORY_DATA_SOURCE or hard-coded "real" should route
 *     through getDataSource() / isFixtureMode() / isRealMode().
 *  2. Fixture mode is gated off in production: setDataSource("fixture") throws
 *     when NODE_ENV === "production", and readDataSourceConfig() never returns
 *     "fixture" in production even if the env var is set.
 *  3. Default is "real". The app fails closed (UNAVAILABLE) when the real
 *     source is not connected — it never silently falls back to fixtures.
 */

export type DataSource = "real" | "fixture";

const DEFAULT_SOURCE: DataSource = "real";

let currentSource: DataSource = DEFAULT_SOURCE;

function isProduction(env: Record<string, string | undefined>): boolean {
  return env.NODE_ENV === "production";
}

/**
 * Read the configured datasource from the environment.
 *
 *   OBSERVATORY_DATA_SOURCE = "fixture" -> fixture (dev / non-production only)
 *   anything else / unset               -> real
 *
 * Never returns "fixture" in production.
 */
export function readDataSourceConfig(
  env: Record<string, string | undefined> = process.env,
): DataSource {
  const raw = env.OBSERVATORY_DATA_SOURCE;
  if (raw === "fixture" && !isProduction(env)) return "fixture";
  return "real";
}

/**
 * Initialize the runtime datasource from the environment. Safe to call once at
 * module load / app startup. Idempotent — calling again resets to the env
 * value, discarding any prior runtime setDataSource() call.
 */
export function initDataSource(
  env?: Record<string, string | undefined>,
): DataSource {
  currentSource = readDataSourceConfig(env);
  return currentSource;
}

/**
 * Get the current runtime datasource.
 */
export function getDataSource(): DataSource {
  return currentSource;
}

/**
 * Switch the runtime datasource. Dev/local only — throws in production to
 * prevent accidentally serving fixture data in a deployed environment.
 */
export function setDataSource(
  source: DataSource,
  env: Record<string, string | undefined> = process.env,
): void {
  if (source === "fixture" && isProduction(env)) {
    throw new Error(
      "dataSource: fixture mode is disabled in production (NODE_ENV=production)",
    );
  }
  currentSource = source;
}

/**
 * True when currently in fixture mode.
 */
export function isFixtureMode(): boolean {
  return currentSource === "fixture";
}

/**
 * True when currently in real mode.
 */
export function isRealMode(): boolean {
  return currentSource === "real";
}

/** Read-only config capabilities; grants no effect. */
export interface DataSourceConfigCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DATA_SOURCE_CONFIG_CAPABILITIES: DataSourceConfigCapabilities =
  Object.freeze({
    read: true,
    write: false,
    approve: false,
    deny: false,
    merge: false,
    deploy: false,
  } as const);

// Initialize on module load from the environment.
initDataSource();
