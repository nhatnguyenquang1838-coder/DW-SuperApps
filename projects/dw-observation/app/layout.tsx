import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DW Run Observatory",
  description: "Read-only historical view of DW SuperApps run projections (M1).",
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
            <a href="/runs" className="text-lg font-semibold">
              DW Run Observatory
            </a>
            <span className="ml-3 text-xs text-muted">
              read-only historical projection
            </span>
          </header>
          <main className="px-6 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
