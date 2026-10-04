import React from "react";
import TopNavigation from "./TopNavigation";

interface WorkspaceShellProps {
  children: React.ReactNode;
  subtitle?: string;
  navItems?: Array<{ href: string; label: string }>;
}

export default function WorkspaceShell({ children, subtitle, navItems }: WorkspaceShellProps) {
  return (
    <div className="min-h-screen" style={{ background: "var(--color-canvas)", color: "var(--color-text-primary)" }}>
      <TopNavigation items={navItems} subtitle={subtitle} />
      <main className="mx-auto max-w-5xl px-6 py-6">{children}</main>
    </div>
  );
}