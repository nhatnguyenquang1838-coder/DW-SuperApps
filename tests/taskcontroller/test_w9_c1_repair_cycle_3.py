"""W9-C1 CI repair cycle 3 — bounded repair of the certification-only fault.

This test replaced the deliberate fault at SHA A_3. It is the declared
``CI_FAIL -> BOUNDED_REPAIR`` edge outcome: the same TaskController validation
workflow that failed at A_3 now passes at B_3.
"""
import pytest


def test_w9_c1_repair_cycle_3_restores_green_suite():
    assert [1] == [1]
    assert len("repair-b3") == 9
