// Server Component — Canonical /dashboard route.
//
// DWO v2: Dashboard is a real, source-backed route — not a redirect,
// not a fixture-only page. Renders from the projection, never fixtures.
//
// Read-only. Grants no effect capability.
//
// Fail-closed: when the source is unavailable, counts render as
// UNAVAILABLE (null), never 0 and never as healthy-by-default.

import { readDashboardProjection } from "@/lib/dashboard/readDashboardProjection";
import Dashboard from "@/components/dwo/Dashboard";

export default async function DashboardPage() {
  // Real source — empty records = source unavailable (fail-closed).
  const projection = readDashboardProjection("real", []);

  return (
    <div
      className="min-h-screen"
      style={{
        background: "var(--dwo-color-bg-canvas)",
        color: "var(--dwo-color-text-primary)",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <Dashboard projection={projection} />
      </div>
    </div>
  );
}