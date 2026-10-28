#!/usr/bin/env python3
"""Materialize one canonical TaskController mailbox/v2 Controller transition.

Input is semantic state, never a pre-rendered GitHub record.  The script owns
GitHub event/cursor rendering through GitHubMailboxRepository and continuation
record rendering through GitHubContinuationStore.

Example:
    GITHUB_TOKEN=... python scripts/taskcontroller_mailbox_materialize.py \
      --repository owner/repo --issue 123 --spec transition.json \
      --ledger /tmp/taskcontroller-ledger.sqlite3

The command never grants G2/G4/G5/G6 authority.  Authority must already be
represented in the fully bound request and is validated by TaskController.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import ControllerContinuation
from taskcontroller.interaction.github_continuation_store import GitHubContinuationStore
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRepository
from taskcontroller.interaction.github_rest_transport import GitHubRestIssueCommentTransport
from taskcontroller.runtime.high_integrity_session import materialize_controller_transition


_ALLOWED_SPEC_KEYS = frozenset(
    {"checkpoint", "request", "state_version", "prepared_at", "committed_at"}
)
_CHECKPOINT_FIELDS = (
    "run_id",
    "controller_epoch",
    "phase",
    "status",
    "next_action",
    "controller_mailbox_ref",
    "controller_seq",
    "executor_actor",
    "executor_mailbox_ref",
    "expected_executor_seq",
    "last_seen_executor_seq",
    "wakeup_binding",
    "exact_head_sha",
    "updated_at",
    "human_root_ref",
)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TaskControllerValidationError(f"{field} must be an object")
    return dict(value)


def _load_spec(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskControllerValidationError(f"cannot read materialization spec: {exc}") from exc
    spec = _mapping(value, "spec")
    unknown = set(spec) - _ALLOWED_SPEC_KEYS
    if unknown:
        raise TaskControllerValidationError(
            "materialization spec contains runtime-owned/unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    missing = _ALLOWED_SPEC_KEYS - set(spec)
    if missing:
        raise TaskControllerValidationError(
            "materialization spec is missing fields: " + ", ".join(sorted(missing))
        )
    return spec


def _checkpoint(value: Any) -> ControllerContinuation:
    raw = _mapping(value, "checkpoint")
    allowed = set(_CHECKPOINT_FIELDS) | {"protocol", "checkpoint_id"}
    unknown = set(raw) - allowed
    if unknown:
        raise TaskControllerValidationError(
            "checkpoint contains unsupported fields: " + ", ".join(sorted(unknown))
        )
    values = {name: raw.get(name) for name in _CHECKPOINT_FIELDS if name in raw}
    return ControllerContinuation(**values)


def _validate_location(repository: str, issue: int, checkpoint: ControllerContinuation) -> None:
    prefix = f"github://{repository}/issues/{issue}#"
    for field, ref in (
        ("controller_mailbox_ref", checkpoint.controller_mailbox_ref),
        ("executor_mailbox_ref", checkpoint.executor_mailbox_ref),
    ):
        if not ref.startswith(prefix):
            raise TaskControllerValidationError(
                f"{field} must bind the selected GitHub repository/issue"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize one deterministic TaskController mailbox/v2 transition"
    )
    parser.add_argument("--repository", required=True, help="GitHub owner/repo")
    parser.add_argument("--issue", required=True, type=int, help="GitHub issue number")
    parser.add_argument("--spec", required=True, type=Path, help="Fully bound semantic transition JSON")
    parser.add_argument(
        "--ledger",
        required=True,
        type=Path,
        help="Local durable TaskController dispatch ledger SQLite path",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing GitHub token (default: GITHUB_TOKEN)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"{args.token_env} is required")

    spec = _load_spec(args.spec)
    checkpoint = _checkpoint(spec["checkpoint"])
    _validate_location(args.repository, args.issue, checkpoint)

    transport = GitHubRestIssueCommentTransport(token)
    repository = GitHubMailboxRepository(transport)
    continuation_store = GitHubContinuationStore(
        transport,
        repository=args.repository,
        issue_number=args.issue,
    )
    ledger = AuditFacade(args.ledger)
    try:
        receipt = materialize_controller_transition(
            continuation_store=continuation_store,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_mapping(spec["request"], "request"),
            state_version=spec["state_version"],
            prepared_at=spec["prepared_at"],
            committed_at=spec["committed_at"],
        )
    finally:
        ledger.close()

    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
