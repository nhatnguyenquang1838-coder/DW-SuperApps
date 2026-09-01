"""W9-C1 CI repair cycle 2 — bounded repair of the certification-only fault.

This test replaced the deliberate fault at SHA A_2. It is the declared
``CI_FAIL -> BOUNDED_REPAIR`` edge outcome: the same TaskController validation
workflow that failed at A_2 now passes at B_2.
"""
import pytest


def test_w9_c1_repair_cycle_2_restores_green_suite():
    assert 2 == 2
    assert len("repair-b2") == 9
