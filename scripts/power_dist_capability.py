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
CSS_UTILITY_TOKEN = re.compile(r"^[A-Za-z0-9_:\-\[\]()./%#]+$")
CSS_UTILITY_PREFIXES = (
    "text-",
    "bg-",
    "border",
    "ring-",
    "shadow-",
    "fill-",
    "stroke-",
    "hover:",
    "focus:",
    "dark:",
)
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


def is_css_style_reference(match_text: str) -> bool:
    """Return true only for assigned CSS references or utility-class lists.

    Dashboard source may legitimately map the node type ``token`` to CSS values,
    for example ``var(--color-node-config)`` or a Tailwind class list. A value is
    exempted only when every whitespace-delimited item is valid CSS utility syntax
    and at least one item carries a recognized style prefix. Arbitrary token-like
    literals remain subject to the configured secret patterns.
    """

    literal_match = TRAILING_QUOTED_LITERAL.search(match_text)
    if not literal_match:
        return False
    literal = literal_match.group(1)
    if CSS_CUSTOM_PROPERTY_REFERENCE.fullmatch(literal):
        return True

    utilities = literal.split()
    return bool(
        utilities
        and all(CSS_UTILITY_TOKEN.fullmatch(utility) for utility in utilities)
        and any(utility.startswith(CSS_UTILITY_PREFIXES) for utility in utilities)
    )


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
                if is_css_style_reference(match.group(0)):
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
