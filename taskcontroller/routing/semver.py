"""WP3 deterministic SemVer comparison (NO GWC, stdlib only).

Bounded comparator: supports MAJOR.MINOR.PATCH with optional pre-release
identifiers. Comparison is numeric per component; malformed versions raise
RoutingEligibilityError (fail closed) when a comparison is required.

We do NOT silently lexicographically compare version strings.
"""

from __future__ import annotations

import re

from taskcontroller.routing.errors import RoutingEligibilityError

_VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


class _Version:
    __slots__ = ("major", "minor", "patch", "pre")

    def __init__(self, major: int, minor: int, patch: int, pre: tuple[str, ...] | None) -> None:
        self.major = major
        self.minor = minor
        self.patch = patch
        self.pre = pre  # None => release; () => empty prerelease; else identifiers

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"{self.major}.{self.minor}.{self.patch}-{self.pre}"


def _split_id(token: str) -> tuple[int | str, ...]:
    """Split a pre-release identifier into a comparable key tuple."""
    # numeric identifiers compare numerically and lower than alphanumeric
    if token.isdigit():
        return (0, int(token))
    return (1, token)


def parse_version(value: str) -> _Version:
    """Parse a semver string; raise RoutingEligibilityError if malformed."""
    if not isinstance(value, str) or not value.strip():
        raise RoutingEligibilityError(f"malformed version (empty): {value!r}")
    m = _VERSION_RE.match(value.strip())
    if m is None:
        raise RoutingEligibilityError(f"malformed semver: {value!r}")
    return _Version(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre=tuple(m.group("pre").split(".")) if m.group("pre") else None,
    )


def compare_versions(a: str, b: str) -> int:
    """Return -1/0/1 comparing semver a vs b. Fail closed on malformed input."""
    va = parse_version(a)
    vb = parse_version(b)
    for x, y in ((va.major, vb.major), (va.minor, vb.minor), (va.patch, vb.patch)):
        if x != y:
            return -1 if x < y else 1
    # release (no pre) > prerelease
    a_pre = va.pre
    b_pre = vb.pre
    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:
        return 1
    if b_pre is None:
        return -1
    if a_pre == b_pre:
        return 0
    for x, y in zip(a_pre, b_pre):
        kx = _split_id(x)
        ky = _split_id(y)
        if kx != ky:
            return -1 if kx < ky else 1
    # shorter prerelease set has lower precedence
    return -1 if len(a_pre) < len(b_pre) else 1


def satisfies_min_version(actual: str, min_version: str) -> bool:
    """True iff actual >= min_version (both semver). Fail closed on malformed."""
    return compare_versions(actual, min_version) >= 0
