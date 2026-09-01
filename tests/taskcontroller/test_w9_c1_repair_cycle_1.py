"""W9-C1 CI repair cycle 1 — bounded repair of the certification-only fault.

This test replaced the deliberate `assert 1 == 2` fault at SHA A_1. It is the
declared ``CI_FAIL -> BOUNDED_REPAIR`` edge outcome: the same TaskController
validation workflow that failed at A_1 now passes at B_1.
"""
import pytest


def test_w9_c1_repair_cycle_1_restores_green_suite():
    assert 1 == 1
    assert len("repair-b1") == 9
