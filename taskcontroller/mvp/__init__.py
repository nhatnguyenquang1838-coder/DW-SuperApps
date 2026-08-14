"""MVP protocol bridge package (NO GWC, no runtime state, no schema authority).

This package contains ONE stateless translation surface between the active
current-main Slack Controller-Executor MVP protocol (``agents/**``, the sole
protocol authority) and the dormant TaskController core library.

It deliberately exposes no engine, no store, no plan/run state machine and no
JSON schema. See ``protocol_bridge`` for the hard rules it upholds.
"""

from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    INTERCEPT,
    PROTOCOL_VERDICTS,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
    ExecutorReport,
    InterceptReason,
    ProtocolVerdict,
    classify_report,
)

__all__ = [
    "CONTINUE",
    "WAIT_CONTROLLER",
    "TERMINAL",
    "INTERCEPT",
    "PROTOCOL_VERDICTS",
    "ContractedSubtask",
    "ExecutorReport",
    "InterceptReason",
    "ProtocolVerdict",
    "classify_report",
]
