#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dw_power_store import (  # noqa: E402,F401
    ConsumerError,
    configure,
    doctor,
    history,
    install,
    main,
    parser,
    rollback,
    safe_extract,
    uninstall,
)

if __name__ == "__main__":
    raise SystemExit(main())
