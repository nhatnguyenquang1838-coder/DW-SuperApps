#!/usr/bin/env python3
from __future__ import annotations

import dw_project_registry as registry

registry.RUNTIME_FILES = tuple(
    dict.fromkeys(
        [
            *registry.RUNTIME_FILES,
            "README.md",
            "docs/POWER_CONSUMER_RUNTIME_V1.md",
            "docs/POWER_RUNTIME_V2.md",
            "docs/PORTABLE_MULTI_HOST_ROUTER.md",
            "docs/MULTI_HOST_SETUP.md",
            "docs/DW_SUPER_SETUP.md",
        ]
    )
)
registry.RUNTIME_DIRS = tuple(
    dict.fromkeys([*registry.RUNTIME_DIRS, "docs/installation", "docs/powers"])
)


if __name__ == "__main__":
    raise SystemExit(registry.main())
