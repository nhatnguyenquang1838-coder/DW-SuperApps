import React from "react";
import Link from "next/link";

interface NavItem {
  href: string;
  label: string;
}

interface TopNavigationProps {
  items?: NavItem[];
  subtitle?: string;
}

/**
 * Product navigation. Dev-only routes (Fixture Lab, simulations) are
 * deliberately NOT in this list: TECH_SPEC §15 requires "dev-only simulations
 * are not primary product navigation". They stay reachable by direct URL, which
 * is how a review lane should work.
 */
const defaultItems: NavItem[] = [
  { href: "/tasks", label: "Tasks" },
  { href: "/runs", label: "Run Explorer" },
];

export default function TopNavigation({ items = defaultItems, subtitle }: TopNavigationProps) {
  return (
    <header
      className="border-b px-6 py-4"
      style={{ borderColor: "var(--color-border)", background: "var(--color-surface)" } as React.CSSProperties}
    >
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between">
          <Link href="/" className="text-lg font-semibold" style={{ color: "var(--color-text-primary)" }}>
            DW Run Observatory
          </Link>
          <nav className="flex gap-4 text-sm">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-xs hover:text-accent"
                style={{ color: "var(--color-text-muted)" }}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        {subtitle && (
          <span className="ml-3 text-xs" style={{ color: "var(--color-text-muted)" }}>
            {subtitle}
          </span>
        )}
      </div>
    </header>
  );
}