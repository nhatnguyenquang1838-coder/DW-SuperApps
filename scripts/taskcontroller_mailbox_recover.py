#!/usr/bin/env python3
"""One-shot, canonical Controller recovery for expired WAIT_EXECUTOR leases.

Run only from an admitted Controller host. This command never grants G2 authority,
creates a Controller execution_request, wakes an Executor, or polls periodically.

Usage:
  python scripts/taskcontroller_mailbox_recover.py \
    --repository nhatnguyenquang1838-coder/gwc --issue 575 \
    --run-id scrum781-q0-20260920T074727Z \
    --expected-head-sha f6fd4121e492b61e8e0781614cd4b627d99ad979

Requires a host-provided GITHUB_TOKEN; do not paste credentials into chat.
Never invoke while canonical RUN_HOLD prohibits Controller recovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from typing import Sequence

from taskcontroller.interaction.continuation import recover_continuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.runtime.high_integrity_session import recover_high_integrity_session

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_PHASE = "WAIT_CONTROLLER"
_EXPECTED_NEXT = "RESOLVE_EXECUTION_AUTHORITY"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    return parser.parse_args(argv)


def recover_once(args: argparse.Namespace, *, observed_at: str | None = None) -> dict:
    """Call the canonical runtime once; read back immutable continuation evidence."""
    if not _SHA40.fullmatch(args.expected_head_sha):
        raise ValueError("--expected-head-sha must be exactly 40 lowercase hex characters")
    if args.issue <= 0 or len(args.repository.split("/")) != 2:
        raise ValueError("invalid GitHub repository or issue binding")
    token = os.environ.get(args.token_env)
    if not token:
        raise ValueError(f"{args.token_env} is required in the authorized Controller environment")

    transport = GitHubRestIssueCommentTransport(token)
    continuation = GitHubContinuationStore(
        transport, repository=args.repository, issue_number=args.issue,
    )
    mailbox = GitHubMailboxRepository(transport)

    # Preflight must happen before any stateful runtime call.
    before = recover_continuation(continuation, args.run_id)
    if before is None:
        raise ValueError("RECOVERY_CONTINUATION_MISSING")
    if before.exact_head_sha != args.expected_head_sha:
        raise ValueError("RECOVERY_HEAD_MISMATCH: refusing to modify another source HEAD")
    if before.phase not in {"WAIT_EXECUTOR", _EXPECTED_PHASE}:
        raise ValueError("RECOVERY_PHASE_INVALID: expected WAIT_EXECUTOR or WAIT_CONTROLLER")
    if before.phase == _EXPECTED_PHASE and before.next_action != _EXPECTED_NEXT:
        raise ValueError("RECOVERY_PHASE_INVALID: different Controller action owns continuation")

    instant = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    recovery = recover_high_integrity_session(
        continuation_store=continuation,
        repository=mailbox,
        run_id=args.run_id,
        observed_at=instant,
    )
    checkpoint = recovery.checkpoint
    if checkpoint.exact_head_sha != args.expected_head_sha:
        raise ValueError("RECOVERY_HEAD_MISMATCH: recovered checkpoint drift")
    if checkpoint.phase != _EXPECTED_PHASE or checkpoint.next_action != _EXPECTED_NEXT:
        raise ValueError(
            "RECOVERY_BOUNDARY_NOT_REACHED: lease is not expired or recovery has not reached "
            "WAIT_CONTROLLER / RESOLVE_EXECUTION_AUTHORITY; no grant issued"
        )

    remote = continuation.latest_receipt(args.run_id, "dw.taskcontroller.continuation/v1")
    if remote is None:
        raise ValueError("RECOVERY_CONTINUATION_RECEIPT_MISSING")
    durable = recover_continuation(continuation, args.run_id)
    if durable != checkpoint:
        raise ValueError("RECOVERY_CONTINUATION_READBACK_MISMATCH")
    return {
        "status": "RECOVERY_CONTINUATION_VERIFIED",
        "authority_granted": False,
        "executor_wakeup_allowed": False,
        "protected_effects_allowed": False,
        "mailbox_event_created": False,
        "run_id": args.run_id,
        "checkpoint": checkpoint.to_dict(),
        "continuation_remote_receipt": remote.to_dict(),
        "controller_cursor": recovery.controller_cursor.to_dict(),
        "next_action": "CONTROLLER_RESOLVE_EXECUTION_AUTHORITY",
        "observed_at": instant,
    }


def main(argv: Sequence[str] | None = None) -> int:
    result = recover_once(_parse_args(argv))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
