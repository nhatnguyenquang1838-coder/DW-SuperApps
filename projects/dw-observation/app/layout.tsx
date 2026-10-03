import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DW Run Observatory",
  description: "Read-only historical view of DW SuperApps run projections (DWO v2).",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-edge px-6 py-4">
            <div className="mx-auto max-w-5xl">
              <div className="flex items-center justify-between">
                <a href="/tasks" className="text-lg font-semibold">
                  DW Run Observatory
                </a>
                <nav className="flex gap-4 text-sm">
                  <a
                    href="/tasks"
                    className="text-xs text-muted hover:text-foreground"
                  >
                    Tasks
                  </a>
                  <a
                    href="/runs"
                    className="text-xs text-muted hover:text-foreground"
                  >
                    Run Explorer
                  </a>
                  <a
                    href="/dev/fixtures"
                    className="text-xs text-muted hover:text-foreground"
                  >
                    Fixtures (dev)
                  </a>
                  <a
                    href="/dev/sim/g0g6"
                    className="text-xs text-muted hover:text-foreground"
                  >
                    Sim G0G6 (dev)
                  </a>
                </nav>
              </div>
              <span className="ml-3 text-xs text-muted">
                read-only historical projection (DWO v2, fail-closed)
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-5xl px-6 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
