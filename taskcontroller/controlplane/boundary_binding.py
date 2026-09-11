"""TC-MBX-307: bind one ExecutionBoundary across v2 records.

The binding layer is a pure Controller-side adapter.  It carries the exact
boundary digest into the request, child contract, attempt, and terminal-result
representations without invoking a provider or changing mailbox state.  A
child boundary is admitted only after the existing executable subset proof
succeeds; a mismatch is never repaired by silently replacing a digest.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from taskcontroller.controlplane.execution_boundary import (
    BoundarySubsetProof,
    ExecutionBoundary,
    ExecutionBoundaryValidationError,
    REPLAN_REQUIRED,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)


Record: TypeAlias = Mapping[str, Any]
BoundaryInput: TypeAlias = ExecutionBoundary | Mapping[str, Any]


def _mailbox_fail(code: str, message: str) -> None:
    raise MailboxV2ValidationError(code, message)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _mailbox_fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be an object")
    return copy.deepcopy(dict(value))


def _boundary(value: BoundaryInput, name: str = "execution boundary") -> ExecutionBoundary:
    if isinstance(value, ExecutionBoundary):
        return value
    if isinstance(value, Mapping):
        return ExecutionBoundary.from_dict(value)
    _mailbox_fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be an ExecutionBoundary object")
    raise AssertionError("_mailbox_fail must raise")


def _put_consistent(record: dict[str, Any], key: str, value: Any, name: str) -> None:
    existing = record.get(key)
    if existing is not None and existing != value:
        _mailbox_fail(
            MailboxV2ErrorCode.BOUNDARY_MISMATCH,
            f"{name} already contains a different {key}",
        )
    record[key] = copy.deepcopy(value)


def _scope_without_digest(boundary: ExecutionBoundary) -> dict[str, Any]:
    scope = boundary.to_dict()
    scope.pop("scope_digest", None)
    return scope


def _validate_scope(record: Mapping[str, Any], boundary: ExecutionBoundary, name: str) -> None:
    """Require a supplied full scope to describe exactly ``boundary``.

    A missing scope is allowed for small attempt/result records.  When a scope
    is present, it is parsed as the executable object rather than compared as
    an untyped collection, so a wider action/path/budget cannot be smuggled in
    by ordering or aliases.
    """

    if "scope" not in record:
        return
    raw_scope = record["scope"]
    if not isinstance(raw_scope, Mapping):
        _mailbox_fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name}.scope must be an object")
    candidate = dict(raw_scope)
    supplied_digest = candidate.pop("scope_digest", None)
    try:
        parsed = ExecutionBoundary.from_dict(candidate)
    except (ExecutionBoundaryValidationError, TypeError) as exc:
        raise exc
    if supplied_digest is not None and supplied_digest != parsed.digest():
        _mailbox_fail(
            MailboxV2ErrorCode.BOUNDARY_MISMATCH,
            f"{name}.scope_digest does not match the supplied scope",
        )
    if parsed.digest() != boundary.digest():
        # Compare the parsed boundary against the bound child.  If it is wider,
        # the existing validator reports the exact REPLAN_REQUIRED dimensions.
        try:
            boundary.validate_child_subset(parsed)
        except ExecutionBoundaryValidationError as exc:
            if exc.code == REPLAN_REQUIRED:
                raise
        _mailbox_fail(
            MailboxV2ErrorCode.BOUNDARY_MISMATCH,
            f"{name}.scope is not bound to {boundary.digest()}",
        )


def _bind_v2_payload(payload: Mapping[str, Any], boundary: ExecutionBoundary) -> dict[str, Any]:
    candidate = _mapping(payload, "v2 envelope")
    logical = _mapping(candidate.get("logical_contract"), "logical_contract")
    identity = _mapping(candidate.get("execution_identity"), "execution_identity")
    attempt = _mapping(candidate.get("attempt"), "attempt")

    _validate_scope(logical, boundary, "logical_contract")
    _put_consistent(logical, "boundary_digest", boundary.digest(), "logical_contract")
    _put_consistent(identity, "boundary_digest", boundary.digest(), "execution_identity")
    _put_consistent(attempt, "boundary_digest", boundary.digest(), "attempt")
    candidate["logical_contract"] = logical
    candidate["execution_identity"] = identity
    candidate["attempt"] = attempt

    result = candidate.get("result")
    if result is not None:
        result_dict = _mapping(result, "result")
        _put_consistent(result_dict, "boundary_digest", boundary.digest(), "result")
        candidate["result"] = result_dict
    return candidate


@dataclass(frozen=True)
class BoundaryBinding:
    """Immutable binding of an execution boundary to protocol records.

    ``BoundaryBinding(boundary)`` is used for a root request/attempt/result.
    ``BoundaryBinding.for_child(parent, child)`` first obtains a
    :class:`BoundarySubsetProof`; the resulting binding carries both the child
    digest and the parent digest when it materializes a child contract.
    """

    boundary: ExecutionBoundary
    parent_boundary: ExecutionBoundary | None = None
    child_depth: int = 0
    subset_proof: BoundarySubsetProof | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, ExecutionBoundary):
            _mailbox_fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "boundary binding requires an ExecutionBoundary",
            )
        if isinstance(self.child_depth, bool) or not isinstance(self.child_depth, int) or self.child_depth < 0:
            _mailbox_fail(MailboxV2ErrorCode.SCHEMA_INVALID, "child_depth must be an integer >= 0")
        if self.parent_boundary is None:
            if self.subset_proof is not None:
                _mailbox_fail(
                    MailboxV2ErrorCode.SCHEMA_INVALID,
                    "a root boundary cannot carry a child subset proof",
                )
            return
        if not isinstance(self.parent_boundary, ExecutionBoundary):
            _mailbox_fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "parent_boundary must be an ExecutionBoundary",
            )
        proof = self.parent_boundary.validate_child_subset(
            self.boundary,
            child_depth=self.child_depth,
        )
        if self.subset_proof is not None and self.subset_proof != proof:
            _mailbox_fail(
                MailboxV2ErrorCode.BOUNDARY_MISMATCH,
                "provided child subset proof does not match the boundaries",
            )
        object.__setattr__(self, "subset_proof", proof)

    @classmethod
    def for_child(
        cls,
        parent: BoundaryInput,
        child: BoundaryInput,
        *,
        child_depth: int = 0,
    ) -> "BoundaryBinding":
        """Create a child binding only after proving a strict parent subset."""

        return cls(
            boundary=_boundary(child, "child boundary"),
            parent_boundary=_boundary(parent, "parent boundary"),
            child_depth=child_depth,
        )

    @property
    def digest(self) -> str:
        return self.boundary.digest()

    @property
    def boundary_digest(self) -> str:
        """Protocol-facing name for :attr:`digest`."""

        return self.digest

    @property
    def parent_digest(self) -> str | None:
        return self.parent_boundary.digest() if self.parent_boundary is not None else None

    def bind_attempt(self, attempt: Record) -> dict[str, Any]:
        """Copy an attempt and bind its digest without mutating the input."""

        result = _mapping(attempt, "attempt")
        _put_consistent(result, "boundary_digest", self.digest, "attempt")
        return result

    def bind_terminal_result(self, result: Record) -> dict[str, Any]:
        """Copy a terminal result and bind its digest without mutating the input."""

        bound = _mapping(result, "terminal result")
        _put_consistent(bound, "boundary_digest", self.digest, "terminal result")
        return bound

    def bind_request(self, envelope: V2MailboxEnvelope | Record) -> V2MailboxEnvelope:
        """Bind and validate a request envelope at the exact v2 wire boundary."""

        raw = envelope.to_dict() if isinstance(envelope, V2MailboxEnvelope) else _mapping(envelope, "request envelope")
        if raw.get("message_type") != "execution_request":
            _mailbox_fail(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "request boundary binding requires message_type=execution_request",
            )
        candidate = _bind_v2_payload(raw, self.boundary)
        candidate["digest"] = canonical_digest(candidate)
        return V2MailboxEnvelope.from_dict(candidate)

    def bind_child_contract(self, contract: Record | V2MailboxEnvelope) -> dict[str, Any] | V2MailboxEnvelope:
        """Bind a plain child contract or a full v2 child envelope.

        Plain contracts carry the parent digest and subset proof beside their
        child digest.  A full v2 envelope stores those two audit values inside
        its unrestricted ``payload`` so the normative logical-contract schema
        remains strict and v1 adapters remain untouched.
        """

        if isinstance(contract, V2MailboxEnvelope):
            candidate = contract.to_dict()
        else:
            candidate = _mapping(contract, "child contract")
        is_envelope = candidate.get("protocol") == "dw.taskcontroller.mailbox/v2"
        if is_envelope:
            candidate = _bind_v2_payload(candidate, self.boundary)
            payload = _mapping(candidate.get("payload"), "child envelope payload")
            if self.parent_digest is not None:
                _put_consistent(payload, "parent_boundary_digest", self.parent_digest, "child envelope payload")
                assert self.subset_proof is not None
                _put_consistent(
                    payload,
                    "boundary_subset_proof",
                    self.subset_proof.to_dict(),
                    "child envelope payload",
                )
            candidate["payload"] = payload
            candidate["digest"] = canonical_digest(candidate)
            return V2MailboxEnvelope.from_dict(candidate)

        _validate_scope(candidate, self.boundary, "child contract")
        _put_consistent(candidate, "boundary_digest", self.digest, "child contract")
        if self.parent_digest is not None:
            _put_consistent(candidate, "parent_boundary_digest", self.parent_digest, "child contract")
            assert self.subset_proof is not None
            _put_consistent(
                candidate,
                "boundary_subset_proof",
                self.subset_proof.to_dict(),
                "child contract",
            )
        return candidate


# Function aliases keep the seam discoverable for adapters that prefer
# verb-oriented names while retaining one implementation and one proof path.
def bind_execution_request(
    envelope: V2MailboxEnvelope | Record,
    boundary: BoundaryInput,
) -> V2MailboxEnvelope:
    return BoundaryBinding(_boundary(boundary)).bind_request(envelope)


def bind_child_contract(
    contract: Record | V2MailboxEnvelope,
    parent_boundary: BoundaryInput,
    child_boundary: BoundaryInput,
    *,
    child_depth: int = 0,
) -> dict[str, Any] | V2MailboxEnvelope:
    return BoundaryBinding.for_child(parent_boundary, child_boundary, child_depth=child_depth).bind_child_contract(contract)


def bind_attempt(attempt: Record, boundary: BoundaryInput) -> dict[str, Any]:
    return BoundaryBinding(_boundary(boundary)).bind_attempt(attempt)


def bind_terminal_result(result: Record, boundary: BoundaryInput) -> dict[str, Any]:
    return BoundaryBinding(_boundary(boundary)).bind_terminal_result(result)


# Descriptive aliases for callers using the architecture vocabulary.
ExecutionBoundaryBinding = BoundaryBinding
bind_request_boundary = bind_execution_request
bind_child_contract_boundary = bind_child_contract
bind_attempt_boundary = bind_attempt
bind_terminal_result_boundary = bind_terminal_result


__all__ = [
    "BoundaryBinding",
    "BoundaryInput",
    "ExecutionBoundaryBinding",
    "Record",
    "bind_attempt",
    "bind_attempt_boundary",
    "bind_child_contract",
    "bind_child_contract_boundary",
    "bind_execution_request",
    "bind_request_boundary",
    "bind_terminal_result",
    "bind_terminal_result_boundary",
]
