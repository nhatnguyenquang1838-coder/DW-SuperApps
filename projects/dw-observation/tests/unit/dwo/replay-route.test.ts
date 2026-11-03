import { describe, expect, it } from "vitest";
import { buildReplayRoute } from "@/lib/dwo/replayRoute";

describe("buildReplayRoute", () => {
  it("keeps an untrusted run id inside one encoded path segment", () => {
    expect(buildReplayRoute("run/?mode=live#fragment", 7)).toBe(
      "/runs/run%2F%3Fmode%3Dlive%23fragment?mode=replay&seq=7"
    );
  });
});
