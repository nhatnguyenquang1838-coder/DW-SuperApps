"""W9-C1 CI fault cycle 2 — deliberate failing test (certification-only).

This file is a temporary, certification-only fault whose sole purpose is to
produce a valid terminal GitHub Actions FAILURE at exact SHA A_2. It touches no
product code, no data, no secrets, and no workflow files. The repair commit
replaces it with a passing test.
"""
import pytest


def test_w9_c1_deliberate_fault_cycle_2():
    assert "cycle-2" == "should-fail", "W9-C1 cycle 2 deliberate fault: must fail CI once"
