import type { Metadata } from "next";
import Link from "next/link";
import TopNavigation from "@/components/dwo/TopNavigation";
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
          {/*
            Navigation is owned by TopNavigation (which uses next/link).
            This layout previously carried its own parallel header built from
            raw <a href> tags — a second nav that drifted, and a TECH_SPEC §15
            violation ("no raw anchor navigation remains where Next Link/router
            semantics are expected"). Dev-only routes are still reachable, but
            they are rendered by TopNavigation outside the primary product nav.
          */}
          <TopNavigation subtitle="read-only historical projection (DWO v2, fail-closed)" />
          <main className="mx-auto max-w-5xl px-6 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}