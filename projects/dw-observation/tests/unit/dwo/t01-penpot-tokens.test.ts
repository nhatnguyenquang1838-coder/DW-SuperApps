/**
 * T01r — Penpot DWO/Core tokens regression guard.
 *
 * Reads globals.css and tailwind.config.ts as text and asserts that every
 * canonical Penpot value from the DWO/Core token set is present.
 * Case-insensitive hex matching so #0B0F14 and #0b0f14 both count.
 */
import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../..");
const CSS = fs.readFileSync(path.join(ROOT, "app/globals.css"), "utf-8");
const TW = fs.readFileSync(path.join(ROOT, "tailwind.config.ts"), "utf-8");

const SOURCE = CSS + "\n" + TW;

/* Canonical Penpot DWO/Core token set — read from Penpot MCP API */
const COLOR_TOKENS: Record<string, string> = {
  "color.bg.canvas": "#0B0F14",
  "color.bg.surface": "#111827",
  "color.bg.subtle": "#17202B",
  "color.border.default": "#2A3441",
  "color.text.primary": "#F3F6FA",
  "color.text.muted": "#9AA6B2",
  "color.text.faint": "#66717F",
  "color.accent.blue": "#4EA1FF",
  "color.state.green": "#48C78E",
  "color.state.amber": "#F5B942",
  "color.state.red": "#FF6B6B",
  "color.state.purple": "#A78BFA",
};

const SPACING_TOKENS: Record<string, string> = {
  "space.4": "4",
  "space.8": "8",
  "space.12": "12",
  "space.16": "16",
  "space.20": "20",
  "space.24": "24",
};

const RADIUS_TOKENS: Record<string, string> = {
  "radius.6": "6",
  "radius.8": "8",
  "radius.10": "10",
  "radius.12": "12",
};

describe("T01r — Penpot DWO/Core canonical tokens", () => {
  for (const [token, value] of Object.entries(COLOR_TOKENS)) {
    it(`has ${token} = ${value} (case-insensitive hex)`, () => {
      const re = new RegExp(value.replace("#", "#"), "i");
      expect(SOURCE).toMatch(re);
    });
  }

  for (const [token, value] of Object.entries(SPACING_TOKENS)) {
    it(`has ${token} = ${value}`, () => {
      expect(SOURCE).toContain(value);
    });
  }

  for (const [token, value] of Object.entries(RADIUS_TOKENS)) {
    it(`has ${token} = ${value}`, () => {
      expect(SOURCE).toContain(value);
    });
  }
});
