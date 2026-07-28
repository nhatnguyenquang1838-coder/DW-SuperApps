#!/usr/bin/env python3
"""Capability-aware wrapper for DW Power distribution builds.

The core builder remains conservative by default. This wrapper enables explicitly
advertised UI/dashboard package surfaces when a distribution recipe declares:

    spec:
      capabilities:
        dashboard: true

Without that capability, dashboard/frontend/web-ui paths remain forbidden.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
POWER_DIST_PATH = ROOT / "scripts" / "power_dist.py"

DASHBOARD_PATTERNS = (
    "dashboard/**",
    "**/dashboard/**",
    "dashboards/**",
    "**/dashboards/**",
    "frontend/**",
    "**/frontend/**",
    "web-ui/**",
    "**/web-ui/**",
)
CSS_CUSTOM_PROPERTY_REFERENCE = re.compile(r"^var\(--[A-Za-z0-9_-]+\)$")
TRAILING_QUOTED_LITERAL = re.compile(r"['\"]([^'\"]+)['\"]\s*$")


def load_power_dist_module():
    spec = importlib.util.spec_from_file_location("power_dist", POWER_DIST_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {POWER_DIST_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dashboard_enabled(recipe: dict[str, Any]) -> bool:
    capabilities = recipe.get("spec", {}).get("capabilities", {})
    return bool(isinstance(capabilities, dict) and capabilities.get("dashboard") is True)


def is_css_custom_property_reference(match_text: str) -> bool:
    """Return true only for an assigned CSS var(--name) literal.

    Source files may legitimately contain mappings such as
    ``token: "var(--color-node-config)"``. That is a style reference, not a
    credential. No other token-like literal is exempted.
    """

    literal = TRAILING_QUOTED_LITERAL.search(match_text)
    return bool(literal and CSS_CUSTOM_PROPERTY_REFERENCE.fullmatch(literal.group(1)))


def patch_power_dist_module(power_dist_module):
    original_forbidden_patterns = power_dist_module._forbidden_patterns

    def capability_forbidden_patterns(recipe: dict[str, Any]) -> tuple[str, ...]:
        patterns = original_forbidden_patterns(recipe)
        if not dashboard_enabled(recipe):
            return patterns
        return tuple(pattern for pattern in patterns if pattern not in DASHBOARD_PATTERNS)

    def capability_scan_secret_content(path: Path, custom_patterns: Iterable[str]) -> None:
        if path.stat().st_size > power_dist_module.MAX_SECRET_SCAN_BYTES:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return

        patterns = list(power_dist_module.DEFAULT_SECRET_PATTERNS)
        for pattern in custom_patterns:
            try:
                patterns.append(re.compile(pattern))
            except re.error as exc:
                raise power_dist_module.DistributionError(
                    f"invalid forbidden content pattern {pattern!r}: {exc}"
                ) from exc

        for pattern in patterns:
            for match in pattern.finditer(text):
                if is_css_custom_property_reference(match.group(0)):
                    continue
                raise power_dist_module.DistributionError(
                    f"forbidden secret-like content in {path}: {pattern.pattern}"
                )

    power_dist_module._forbidden_patterns = capability_forbidden_patterns
    power_dist_module._scan_secret_content = capability_scan_secret_content
    return power_dist_module


def main(argv: list[str] | None = None) -> int:
    power_dist = patch_power_dist_module(load_power_dist_module())
    return power_dist.main(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
