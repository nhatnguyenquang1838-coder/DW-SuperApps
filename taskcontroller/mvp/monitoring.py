"""MVP Controller monitoring loop — in-session 60s polling (NO GWC, NO transport).

Authority
---------
``agents/shared/slack-controller-executor-protocol.md`` defines the Controller
monitoring loop exactly as::

    send contract / command
    -> sleep 60s in-session
    -> read only thread replies newer than last_seen_ts
    -> compare report with expected subtask/milestone
    -> OK: continue polling or release next step
    -> WAIT_CONTROLLER: review before release
    -> DRIFT: INTERCEPT
    -> terminal: leave current control loop

    Polling itself produces no Slack message.

This module is that loop's engine. It is NOT a scheduler, NOT a reminder, NOT a
background job, and NOT a live Slack/Hermes adapter (#52 binds concrete
adapters). Every side effect — sleeping, reading replies, updating the RootCard —
is a narrow injected callable, so the engine itself performs no I/O.

Hard rules upheld here
----------------------
1. IN-SESSION ONLY. ``run_monitoring_loop`` is a plain synchronous call that
   returns a boundary. No thread, no task, no process, no detached execution, no
   scheduler/reminder/automation import.
2. DEFAULT CADENCE IS EXACTLY 60 SECONDS (:data:`POLL_INTERVAL_SECONDS`). Tests
   inject a fake sleeper, so no unit test ever really sleeps.
3. EXPLICIT ``last_seen_ts``. Only strictly newer replies are considered;
   duplicates and older replies are ignored and never re-classified.
4. POLLING IS SILENT. A poll that finds nothing emits nothing: no heartbeat, no
   status ping, no RootCard update.
5. ROOTCARD UPDATES ONLY ON MATERIAL CHANGE. The update callback fires only when
   the verdict or the accumulated evidence actually changed.
6. VERDICTS COME FROM THE WP1 PURE CLASSIFIER. This module never invents a
   verdict and never widens the vocabulary. Malformed reports fail closed —
   never degrading to ``CONTINUE``.
7. BOUNDARIES STOP DELEGATED CONTINUATION. ``WAIT_CONTROLLER``, ``INTERCEPT``
   and ``TERMINAL`` all return immediately. ``TERMINAL`` closes the delegated
   control segment only: it is NOT runtime ``DONE`` and grants no
   ``APPROVE`` / ``MERGE`` authority.
8. NO DEFERRED FULL-E2E DEPENDENCY. Nothing from ``controlplane`` / ``runtime`` /
   ``projections`` / ``routing`` / ``execution`` / ``packs`` is imported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    INTERCEPT,
    PROTOCOL_VERDICTS,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
    ExecutorReport,
    ProtocolVerdict,
    classify_report,
)

#: Production/default in-session cadence, in seconds. Exactly 60 per the MVP doc.
POLL_INTERVAL_SECONDS = 60

#: Verdicts that end the delegated monitoring segment at that boundary.
BOUNDARY_VERDICTS = (WAIT_CONTROLLER, INTERCEPT, TERMINAL)

#: Loop outcome reasons.
REASON_BOUNDARY = "boundary_verdict"
REASON_MAX_POLLS = "max_polls_exhausted"
LOOP_REASONS = (REASON_BOUNDARY, REASON_MAX_POLLS)


# --------------------------------------------------------------------------
# Narrow injected interfaces (transport stays outside).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ThreadReply:
    """One thread reply, newer-than-``last_seen_ts`` filtering key included.

    ``ts`` is an opaque monotonic-comparable string timestamp (Slack ``ts``
    shape). ``payload`` is the raw executor report mapping; it is validated by
    the WP1 ``ExecutorReport`` contract, never trusted as-is.
    """

    ts: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.ts, str) or not self.ts.strip():
            raise TaskControllerValidationError("reply ts must be a non-empty string")
        if not isinstance(self.payload, Mapping):
            raise TaskControllerValidationError("reply payload must be a mapping")


class ReplyReader(Protocol):
    """Reads thread replies. Implementations are bound in #52, not here."""

    def __call__(self, last_seen_ts: str | None) -> Sequence[ThreadReply]:
        ...


#: Sleeper: called with the cadence in seconds. Tests inject a fake.
Sleeper = Callable[[int], None]

#: RootCard updater: called ONLY on a material change.
RootCardUpdater = Callable[["LoopObservation"], None]


def _no_update(observation: "LoopObservation") -> None:
    """Default updater: do nothing. Polling stays silent by default."""
    return None


# --------------------------------------------------------------------------
# Observations / outcome
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LoopObservation:
    """One classified, material observation of the delegated segment.

    Carries the validated immutable ``ExecutorReport`` itself, so the RootCard
    updater can render exactly the values that caused the update
    (``status`` -> progress, ``completed`` -> progress, ``finding_risk`` ->
    risk/blocker, ``next_action`` -> Next, ``evidence`` -> last material update).

    ``evidence`` is exposed as a read-only convenience property delegating to the
    report, so there is exactly ONE source of truth and no duplication drift.
    """

    poll: int
    reply_ts: str
    verdict: ProtocolVerdict
    report: ExecutorReport

    def __post_init__(self) -> None:
        if isinstance(self.poll, bool) or not isinstance(self.poll, int) or self.poll < 1:
            raise TaskControllerValidationError("poll must be an int >= 1")
        if not isinstance(self.reply_ts, str) or not self.reply_ts.strip():
            raise TaskControllerValidationError("reply_ts must be a non-empty string")
        if not isinstance(self.verdict, ProtocolVerdict):
            raise TaskControllerValidationError("verdict must be a ProtocolVerdict")
        if not isinstance(self.report, ExecutorReport):
            raise TaskControllerValidationError("report must be an ExecutorReport")

    # -- material fields, delegated (no copies, no drift) --------------------
    @property
    def subtask_id(self) -> str:
        return self.report.subtask_id

    @property
    def status(self) -> str:
        return self.report.status

    @property
    def completed(self) -> tuple[str, ...]:
        return self.report.completed

    @property
    def evidence(self) -> tuple[str, ...]:
        return self.report.evidence

    @property
    def finding_risk(self) -> tuple[str, ...]:
        return self.report.finding_risk

    @property
    def next_action(self) -> str:
        return self.report.next_action

    @property
    def after(self) -> str:
        return self.report.after

    def to_dict(self) -> dict[str, Any]:
        """Deterministic projection, including the complete report."""
        return {
            "poll": self.poll,
            "reply_ts": self.reply_ts,
            "verdict": self.verdict.to_dict(),
            "report": self.report.to_dict(),
            "status": self.status,
            "completed": list(self.completed),
            "evidence": list(self.evidence),
            "finding_risk": list(self.finding_risk),
            "next_action": self.next_action,
        }


class MalformedReportError(TaskControllerValidationError):
    """A reply could not be validated as a complete ExecutorReport.

    Fail closed: the loop raises instead of treating the poll as ``CONTINUE``.
    """


@dataclass(frozen=True)
class LoopOutcome:
    """The result of one in-session monitoring segment."""

    verdict: str | None
    reason: str
    polls: int
    last_seen_ts: str | None
    observations: tuple[LoopObservation, ...] = field(default_factory=tuple)
    detail: str = ""

    def __post_init__(self) -> None:
        if self.verdict is not None and self.verdict not in PROTOCOL_VERDICTS:
            raise TaskControllerValidationError(f"invalid verdict: {self.verdict!r}")
        if self.reason not in LOOP_REASONS:
            raise TaskControllerValidationError(f"invalid reason: {self.reason!r}")
        if isinstance(self.polls, bool) or not isinstance(self.polls, int) or self.polls < 0:
            raise TaskControllerValidationError("polls must be a non-negative int")

    # -- boundary semantics --------------------------------------------------
    @property
    def is_boundary(self) -> bool:
        return self.verdict in BOUNDARY_VERDICTS

    @property
    def delegated_segment_closed(self) -> bool:
        """True only for TERMINAL: the delegated control segment is closed."""
        return self.verdict == TERMINAL

    @property
    def runtime_done(self) -> bool:
        """TERMINAL is never runtime DONE. Structurally always False."""
        return False

    @property
    def grants_authority(self) -> bool:
        """No loop outcome ever grants APPROVE/MERGE authority."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "polls": self.polls,
            "last_seen_ts": self.last_seen_ts,
            "detail": self.detail,
            "observations": [o.to_dict() for o in self.observations],
            "delegated_segment_closed": self.delegated_segment_closed,
            "runtime_done": self.runtime_done,
            "grants_authority": self.grants_authority,
        }


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------
#: Every ExecutorReport field the MVP RootCard actually surfaces. A change in
#: ANY of these is material: status feeds progress, completed feeds progress,
#: evidence feeds the last material update, finding_risk feeds risk/blocker, and
#: next_action feeds Next.
MATERIAL_REPORT_FIELDS = (
    "status",
    "completed",
    "evidence",
    "finding_risk",
    "next_action",
)


def material_signature(
    report: ExecutorReport, verdict: ProtocolVerdict
) -> tuple[Any, ...]:
    """Deterministic material-change signature for one classified report.

    Covers every user-visible/material ``ExecutorReport`` field
    (:data:`MATERIAL_REPORT_FIELDS`) plus the verdict, its intercept reason and
    its detail — i.e. everything the MVP RootCard can render.

    Deliberately a normalized tuple of primitives: NOT object identity, NOT
    ``repr``, NOT JSON/pickle. Two reports that carry the same material content
    produce the same signature regardless of object identity or field order in
    the source payload, so an identical repeated report stays deduped.
    """
    if not isinstance(report, ExecutorReport):
        raise TaskControllerValidationError("report must be an ExecutorReport")
    if not isinstance(verdict, ProtocolVerdict):
        raise TaskControllerValidationError("verdict must be a ProtocolVerdict")
    return (
        report.subtask_id,
        report.status,
        tuple(report.completed),
        tuple(report.evidence),
        tuple(report.finding_risk),
        report.next_action,
        report.after,
        verdict.verdict,
        verdict.intercept_reason or "",
        verdict.detail,
    )


def _ts_key(ts: str) -> tuple[int, int, int, str]:
    """Lossless ordering key for a reply ts.

    Slack-style ``ts`` values are numeric strings, so a plain lexicographic
    compare is WRONG (``"99.0" > "100.0"``). ``float()`` would order correctly at
    present Slack scale but is lossy in principle, so canonical
    ``seconds.microseconds`` is split and compared as EXACT INTEGERS. Non-numeric
    values fall back to a stable lexicographic bucket.
    """
    if isinstance(ts, str):
        candidate = ts.strip()
        seconds, _, fraction = candidate.partition(".")
        if seconds.isdigit() and (fraction == "" or fraction.isdigit()):
            # Normalize the fractional part so 1.5 and 1.500000 compare equal.
            micros = int((fraction + "000000")[:6]) if fraction else 0
            return (0, int(seconds), micros, "")
    return (1, 0, 0, ts if isinstance(ts, str) else repr(ts))


def _is_newer(ts: str, last_seen_ts: str | None) -> bool:
    """True when ``ts`` is strictly newer than the cursor."""
    if last_seen_ts is None:
        return True
    return _ts_key(ts) > _ts_key(last_seen_ts)


def _newer_replies(
    replies: Sequence[ThreadReply], last_seen_ts: str | None
) -> list[ThreadReply]:
    """Only strictly-newer replies, in ascending ts order. Duplicates ignored."""
    if replies is None:
        return []
    if isinstance(replies, (str, bytes)) or not isinstance(replies, Sequence):
        raise TaskControllerValidationError("reader must return a sequence of ThreadReply")
    for reply in replies:
        if not isinstance(reply, ThreadReply):
            raise TaskControllerValidationError("reader must return ThreadReply objects")
    fresh = [r for r in replies if _is_newer(r.ts, last_seen_ts)]
    seen: set[str] = set()
    unique: list[ThreadReply] = []
    for reply in sorted(fresh, key=lambda r: _ts_key(r.ts)):
        if reply.ts in seen:
            continue
        seen.add(reply.ts)
        unique.append(reply)
    return unique


def run_monitoring_loop(
    contracted: ContractedSubtask,
    read_replies: ReplyReader,
    sleeper: Sleeper,
    last_seen_ts: str | None = None,
    max_polls: int = 1,
    poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    update_rootcard: RootCardUpdater = _no_update,
) -> LoopOutcome:
    """Run the in-session Controller monitoring loop.

    Each poll: sleep the cadence, read only replies newer than ``last_seen_ts``,
    validate each as a complete ``ExecutorReport``, classify it against the
    active contracted subtask, and act on the verdict:

    * ``CONTINUE``        -> keep monitoring (next poll)
    * ``WAIT_CONTROLLER`` -> return the review boundary immediately
    * ``INTERCEPT``       -> return the bounded drift/correction boundary
    * ``TERMINAL``        -> close the delegated control segment only

    Purely in-session and synchronous. Malformed replies raise
    ``MalformedReportError`` (fail closed). Returns when a boundary verdict is
    reached or ``max_polls`` is exhausted.
    """
    if not isinstance(contracted, ContractedSubtask):
        raise TaskControllerValidationError("contracted must be a ContractedSubtask")
    if not callable(read_replies):
        raise TaskControllerValidationError("read_replies must be callable")
    if not callable(sleeper):
        raise TaskControllerValidationError("sleeper must be callable")
    if not callable(update_rootcard):
        raise TaskControllerValidationError("update_rootcard must be callable")
    if isinstance(max_polls, bool) or not isinstance(max_polls, int) or max_polls < 1:
        raise TaskControllerValidationError("max_polls must be an int >= 1")
    if (
        isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, int)
        or poll_interval_seconds < 1
    ):
        raise TaskControllerValidationError("poll_interval_seconds must be an int >= 1")
    if last_seen_ts is not None and (
        not isinstance(last_seen_ts, str) or not last_seen_ts.strip()
    ):
        raise TaskControllerValidationError("last_seen_ts must be a non-empty string or None")

    cursor = last_seen_ts
    observations: list[LoopObservation] = []
    last_verdict: str | None = None
    last_signature: tuple[Any, ...] | None = None

    for poll in range(1, max_polls + 1):
        sleeper(poll_interval_seconds)
        replies = _newer_replies(read_replies(cursor), cursor)

        # Silent poll: nothing new -> no observation, no update, no message.
        if not replies:
            continue

        for reply in replies:
            cursor = reply.ts
            try:
                report = ExecutorReport.from_payload(reply.payload)
            except TaskControllerValidationError as exc:
                raise MalformedReportError(
                    f"malformed executor report at ts {reply.ts}: {exc}"
                ) from exc

            verdict = classify_report(contracted, report)

            # Material change = ANY user-visible report field or verdict state
            # changed. Evidence alone is not enough: status / completed /
            # finding_risk / next_action drive RootCard progress, risk and Next.
            signature = material_signature(report, verdict)
            material = signature != last_signature
            observation = LoopObservation(
                poll=poll,
                reply_ts=reply.ts,
                verdict=verdict,
                report=report,
            )
            if material:
                observations.append(observation)
                update_rootcard(observation)
            last_verdict = verdict.verdict
            last_signature = signature

            if verdict.verdict in BOUNDARY_VERDICTS:
                return LoopOutcome(
                    verdict=verdict.verdict,
                    reason=REASON_BOUNDARY,
                    polls=poll,
                    last_seen_ts=cursor,
                    observations=tuple(observations),
                    detail=verdict.detail,
                )

    return LoopOutcome(
        verdict=last_verdict,
        reason=REASON_MAX_POLLS,
        polls=max_polls,
        last_seen_ts=cursor,
        observations=tuple(observations),
        detail="monitoring budget exhausted without a boundary verdict",
    )
