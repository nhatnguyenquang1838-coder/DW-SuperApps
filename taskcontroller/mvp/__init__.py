"""MVP TaskController package (NO GWC, no runtime state, no schema authority).

The active current-main surface contains two small deterministic pieces:

- ``activation``: explicit TaskController mention -> canonical host load plan.
- ``protocol_bridge``: contracted Executor report -> MVP controller verdict.

The richer TaskController core remains a dormant Full-E2E library unless current
repository policy explicitly activates it.
"""

from taskcontroller.mvp.activation import (
    TASKCONTROLLER_ALIASES,
    TaskControllerActivationPlan,
    mentions_taskcontroller,
    resolve_taskcontroller_activation,
)
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
    "TASKCONTROLLER_ALIASES",
    "TaskControllerActivationPlan",
    "mentions_taskcontroller",
    "resolve_taskcontroller_activation",
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
