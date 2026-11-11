/** Datasource config tests — SCRUM-853 datasource switch. */
import { describe, expect, it } from "vitest";
import {
  readDataSourceConfig,
  initDataSource,
  getDataSource,
  setDataSource,
  isFixtureMode,
  isRealMode,
  DATA_SOURCE_CONFIG_CAPABILITIES,
  type DataSource,
} from "@/lib/dwo/dataSourceConfig";

function envWith(overrides: Record<string, string | undefined>): Record<string, string | undefined> {
  return { ...process.env, ...overrides };
}

describe("readDataSourceConfig", () => {
  it("defaults to 'real' when OBSERVATORY_DATA_SOURCE is unset", () => {
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: undefined }))).toBe("real");
    expect(readDataSourceConfig(envWith({}))).toBe("real");
  });

  it("returns 'fixture' when OBSERVATORY_DATA_SOURCE=fixture in non-production", () => {
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: "fixture", NODE_ENV: "development" }))).toBe("fixture");
  });

  it("never returns 'fixture' in production even when env says fixture", () => {
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: "fixture", NODE_ENV: "production" }))).toBe("real");
  });

  it("returns 'real' for any other env value", () => {
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: "real" }))).toBe("real");
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: "mock" }))).toBe("real");
    expect(readDataSourceConfig(envWith({ OBSERVATORY_DATA_SOURCE: "" }))).toBe("real");
  });
});

describe("initDataSource / getDataSource", () => {
  it("initializes from env and getDataSource reflects it", () => {
    initDataSource(envWith({ OBSERVATORY_DATA_SOURCE: "fixture", NODE_ENV: "development" }));
    expect(getDataSource()).toBe("fixture");

    initDataSource(envWith({ OBSERVATORY_DATA_SOURCE: undefined, NODE_ENV: "development" }));
    expect(getDataSource()).toBe("real");
  });
});

describe("setDataSource", () => {
  it("switches to fixture and back at runtime", () => {
    setDataSource("fixture", envWith({ NODE_ENV: "development" }));
    expect(isFixtureMode()).toBe(true);
    expect(isRealMode()).toBe(false);

    setDataSource("real", envWith({ NODE_ENV: "development" }));
    expect(isRealMode()).toBe(true);
    expect(isFixtureMode()).toBe(false);
  });

  it("throws in production", () => {
    expect(() => setDataSource("fixture", envWith({ NODE_ENV: "production" }))).toThrow(/production/);
    // real in production is allowed
    expect(() => setDataSource("real", envWith({ NODE_ENV: "production" }))).not.toThrow();
    expect(isRealMode()).toBe(true);
  });
});

describe("capabilities", () => {
  it("grants no effect capability", () => {
    expect(DATA_SOURCE_CONFIG_CAPABILITIES).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
  });
});
