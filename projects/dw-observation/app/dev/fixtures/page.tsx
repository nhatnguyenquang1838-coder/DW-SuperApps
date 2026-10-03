// Server Component (Next.js App Router) — dev/review fixture catalog.
//
// /dev/fixtures renders the DWO-UR-30-V1 30-fixture pack from fixtureSpec.ts.
// This is a development-only certification surface: NOT part of primary
// navigation, NOT in the product run-history path.
//
// Read-only. Grants no effect capability.

import { FIXTURE_CATALOG, assertFixtureCatalogInvariants } from "@/lib/dwo/fixtureSpec";

export default function DevFixturesPage() {
  try {
    assertFixtureCatalogInvariants(FIXTURE_CATALOG);
  } catch (e) {
    return (
      <div className="p-6">
        <p className="text-red-600">Fixture catalog invariant violation: {(e as Error).message}</p>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#ffffff",
        color: "#37352f",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <style>{`
        .notion-run-card { border-color: #e9e9e7; background: #ffffff; }
        .notion-run-card:hover { border-color: #37352f; }
        .notion-link-btn { border-color: #d3d1cb; background: #f7f7f5; color: #37352f; }
        .notion-link-btn:hover { background: #efefed; }
      `}</style>
      <div className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="mb-1 text-2xl font-bold tracking-tight" style={{ color: "#37352f" }}>
          Fixture catalog — DWO-UR-30-V1
        </h1>
        <p className="mb-6 text-xs" style={{ color: "#787774" }}>
          29 conforming + 1 negative (DEV-RUN-020). Development/review surface only.
        </p>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {FIXTURE_CATALOG.map((f) => (
            <div
              key={f.id}
              className="notion-run-card rounded border px-3 py-2 text-xs"
              style={{ borderColor: "#e9e9e7", background: "#ffffff", color: "#37352f" }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold" style={{ color: "#37352f" }}>{f.id}</span>
                <span
                  className="rounded px-1.5 py-0.5 text-[10px] uppercase"
                  style={{
                    background: f.kind === "NEGATIVE" ? "#fce4e4" : "#f1f1ef",
                    color: f.kind === "NEGATIVE" ? "#b54708" : "#787774",
                  }}
                >
                  {f.kind}
                </span>
              </div>
              <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                <dt style={{ color: "#9b9a97" }}>domain</dt><dd style={{ color: "#37352f" }}>{f.domain}</dd>
                <dt style={{ color: "#9b9a97" }}>gate</dt><dd style={{ color: "#37352f" }}>{f.gate ?? "—"}</dd>
                <dt style={{ color: "#9b9a97" }}>runState</dt><dd style={{ color: "#37352f" }}>{f.runState}</dd>
                <dt style={{ color: "#9b9a97" }}>auth</dt><dd style={{ color: "#37352f" }}>{f.authorityState}</dd>
                <dt style={{ color: "#9b9a97" }}>purpose</dt><dd style={{ color: "#787774" }}>{f.purpose}</dd>
              </dl>
              {f.children.length > 0 && (
                <div className="mt-1 text-[10px]" style={{ color: "#9b9a97" }}>children: {f.children.join(", ")}</div>
              )}
              {f.deps.length > 0 && (
                <div className="text-[10px]" style={{ color: "#9b9a97" }}>deps: {f.deps.join(", ")}</div>
              )}
            </div>
          ))}
        </div>

        <a
          href="/tasks"
          className="notion-link-btn mt-8 inline-block rounded border px-3 py-1.5 text-sm"
        >
          ← Tasks
        </a>
      </div>
    </div>
  );
}
