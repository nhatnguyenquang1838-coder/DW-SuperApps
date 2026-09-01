"""W9-C1 CI fault cycle 1 — deliberate failing test (certification-only).

This file is a temporary, certification-only fault whose sole purpose is to
produce a valid terminal GitHub Actions FAILURE at exact SHA A_1. It touches no
product code, no data, no secrets, and no workflow files. The repair commit
removes it.
"""
import pytest


def test_w9_c1_deliberate_fault_cycle_1():
    assert 1 == 2, "W9-C1 cycle 1 deliberate fault: must fail CI once"
