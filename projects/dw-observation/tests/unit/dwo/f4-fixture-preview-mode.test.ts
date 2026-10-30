/** F4 — local fixture-preview mode must be explicit and production-disabled. */
import { describe, expect, it } from "vitest";
import { isLocalFixturePreview } from "@/lib/dwo/fixturePreviewMode";

describe("isLocalFixturePreview", () => {
  it("enables the fixture UI only for an explicit non-production fixture mode", () => {
    expect(isLocalFixturePreview({ NODE_ENV: "development", OBSERVATORY_DATA_SOURCE: "fixture" })).toBe(true);
    expect(isLocalFixturePreview({ NODE_ENV: "test", OBSERVATORY_DATA_SOURCE: "fixture" })).toBe(true);
  });

  it("keeps fixture routing disabled for production or implicit sources", () => {
    expect(isLocalFixturePreview({ NODE_ENV: "production", OBSERVATORY_DATA_SOURCE: "fixture" })).toBe(false);
    expect(isLocalFixturePreview({ NODE_ENV: "development", OBSERVATORY_DATA_SOURCE: "real" })).toBe(false);
    expect(isLocalFixturePreview({ NODE_ENV: "development" })).toBe(false);
  });
});
