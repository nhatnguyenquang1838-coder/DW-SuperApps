#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dw_power_store.common import ConsumerError  # noqa: E402
from dw_power_store.compatibility import validate_lock  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the DW Power compatibility lock.")
    parser.add_argument("--strict", action="store_true", help="reserved for CI compatibility")
    parser.parse_args(argv)
    try:
        print(json.dumps(validate_lock(), indent=2, sort_keys=True))
        return 0
    except ConsumerError as exc:
        print(f"power-compatibility: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
