"""Normative, additive TaskController mailbox/v2 contract primitives.

This module intentionally does not persist events or dispatch workers.  It owns
only the machine contract needed by those later layers: schema validation,
canonical bytes/digests, identity checks, per-producer cursor semantics and
explicit protocol negotiation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, NoReturn, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from taskcontroller.errors import TaskControllerValidationError


V1_PROTOCOL = "dw.taskcontroller.a2a/v1"
V2_PROTOCOL = "dw.taskcontroller.mailbox/v2"
SOURCE_MANIFEST_VERSION = "dw-source-manifest-json/v1"


class MailboxV2ErrorCode:
    """Stable machine-readable validation and migration outcomes."""

    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    PROTOCOL_DOWNGRADE_UNSUPPORTED = "PROTOCOL_DOWNGRADE_UNSUPPORTED"
    INVALID_SEQUENCE = "INVALID_SEQUENCE"
    STALE_GENERATION = "STALE_GENERATION"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    MANIFEST_VERSION_MISMATCH = "MANIFEST_VERSION_MISMATCH"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"


class MailboxV2ValidationError(TaskControllerValidationError):
    """Validation error with a stable protocol-level ``code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        errors: Optional[list[Any]] = None,
    ) -> None:
        self.code = code
        super().__init__(f"{code}: {message}", errors=errors or [])


_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "mailbox_v2.schema.json"
_SCHEMA_CACHE: Optional[dict[str, Any]] = None


def get_v2_schema() -> dict[str, Any]:
    """Return a defensive copy of the normative v2 JSON Schema."""

    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        try:
            loaded = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(loaded)
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                f"cannot load normative schema: {exc}",
            ) from exc
        _SCHEMA_CACHE = loaded
    assert _SCHEMA_CACHE is not None
    return copy.deepcopy(_SCHEMA_CACHE)


def _fail(code: str, message: str, *, errors: Optional[list[Any]] = None) -> NoReturn:
    raise MailboxV2ValidationError(code, message, errors=errors)


def canonical_bytes(value: Mapping[str, Any], *, exclude_digest: bool = True) -> bytes:
    """Serialize a JSON object deterministically as UTF-8 bytes.

    Only the envelope's top-level ``digest`` field is omitted.  Omitted keys
    and explicit JSON ``null`` remain distinct because the value is otherwise
    serialized without default insertion or normalization.
    """

    if not isinstance(value, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "canonical value must be an object")
    candidate = copy.deepcopy(dict(value))
    if exclude_digest:
        candidate.pop("digest", None)
    try:
        return json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"value is not canonical JSON: {exc}")
    raise AssertionError("_fail must raise")


def canonical_digest(value: Mapping[str, Any]) -> str:
    """Return the v2 ``sha256:<hex>`` digest of canonical envelope bytes."""

    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _schema_errors(payload: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(get_v2_schema())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in errors
    ]


def _validate_identity_consistency(payload: Mapping[str, Any]) -> None:
    logical = payload["logical_contract"]
    attempt = payload["attempt"]
    identity = payload["execution_identity"]

    if identity["run_id"] != payload["run_id"] or identity["node_id"] != payload["node_id"]:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "execution identity does not bind run/node")
    if identity["plan_version"] != logical["plan_version"]:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "plan version is not bound to logical contract")
    if identity["contract_digest"] != logical["contract_digest"]:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "contract digest is not bound to logical contract")
    if identity["boundary_digest"] != logical["boundary_digest"]:
        _fail(MailboxV2ErrorCode.BOUNDARY_MISMATCH, "boundary digest is not bound to logical contract")
    if identity["source_digest"] != logical["source_digest"]:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "source digest is not bound to logical contract")
    if identity["attempt_id"] != attempt["attempt_id"]:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "attempt ID is not bound to attempt")
    if identity["lease_generation"] != attempt["lease_generation"]:
        _fail(MailboxV2ErrorCode.STALE_GENERATION, "lease generation is not self-consistent")
    if identity["fencing_token"] != attempt["fencing_token"]:
        _fail(MailboxV2ErrorCode.STALE_GENERATION, "fencing token is not bound to attempt")
    if payload["source_manifest"]["digest"] != logical["source_digest"]:
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "source manifest digest differs from contract source digest")


@dataclass(frozen=True)
class V2MailboxEnvelope:
    """Validated immutable-in-use representation of one v2 envelope.

    The mapping is copied on construction and on readback.  Persistence and
    state advancement remain responsibilities of WP2/WP3 adapters.
    """

    _payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_payload", copy.deepcopy(dict(self._payload)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "V2MailboxEnvelope":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "envelope must be a JSON object")
        candidate = copy.deepcopy(dict(payload))
        if candidate.get("protocol") != V2_PROTOCOL:
            _fail(
                MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL,
                f"expected {V2_PROTOCOL}, got {candidate.get('protocol')!r}",
            )
        errors = _schema_errors(candidate)
        if errors:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "schema validation failed", errors=errors)
        if candidate["source_manifest"]["manifest_version"] != SOURCE_MANIFEST_VERSION:
            _fail(
                MailboxV2ErrorCode.MANIFEST_VERSION_MISMATCH,
                f"expected {SOURCE_MANIFEST_VERSION}",
            )
        _validate_identity_consistency(candidate)
        expected_digest = canonical_digest(candidate)
        if candidate["digest"] != expected_digest:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                f"expected {expected_digest}, got {candidate['digest']}",
            )
        return cls(candidate)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._payload))

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self._payload)

    def digest(self) -> str:
        return canonical_digest(self._payload)

    @property
    def protocol(self) -> str:
        return self._payload["protocol"]

    @property
    def run_id(self) -> str:
        return self._payload["run_id"]

    @property
    def node_id(self) -> str:
        return self._payload["node_id"]

    @property
    def seq(self) -> int:
        return self._payload["seq"]

    @property
    def producer_namespace(self) -> str:
        return self._payload["producer"]["namespace"]

    @property
    def idempotency_key(self) -> str:
        return self._payload["idempotency_key"]

    @property
    def logical_contract(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload["logical_contract"])

    @property
    def attempt(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload["attempt"])

    @property
    def execution_identity(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload["execution_identity"])

    def validate_current_generation(self, expected_generation: int) -> None:
        """Reject an event that is not from the current lease generation."""

        if self.execution_identity["lease_generation"] != expected_generation:
            _fail(
                MailboxV2ErrorCode.STALE_GENERATION,
                f"expected lease generation {expected_generation}",
            )

    def validate_current_identity(self, expected: Mapping[str, Any]) -> None:
        """Compare caller-owned current identity without advancing state."""

        actual = self.execution_identity
        for key, expected_value in expected.items():
            if key not in actual:
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"unknown identity key {key!r}")
            if actual[key] == expected_value:
                continue
            if key == "lease_generation":
                _fail(MailboxV2ErrorCode.STALE_GENERATION, "lease generation is stale")
            if key == "boundary_digest":
                _fail(MailboxV2ErrorCode.BOUNDARY_MISMATCH, "boundary digest differs")
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, f"identity field {key!r} differs")


@dataclass(frozen=True)
class MailboxV2Cursor:
    """Per-producer monotonic cursor with idempotent duplicate handling."""

    actor_namespace: str
    last_seq: int = -1
    idempotency_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.actor_namespace:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "cursor actor namespace is required")
        if self.last_seq < -1:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "cursor sequence cannot be below -1")
        object.__setattr__(self, "idempotency_digests", dict(self.idempotency_digests))

    def observe(self, envelope: V2MailboxEnvelope) -> "MailboxV2Cursor":
        if envelope.producer_namespace != self.actor_namespace:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "producer namespace does not match cursor")
        existing = self.idempotency_digests.get(envelope.idempotency_key)
        if existing is not None:
            if existing == envelope.digest():
                return self
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "idempotency key was reused with a different digest",
            )
        if envelope.seq <= self.last_seq:
            _fail(
                MailboxV2ErrorCode.INVALID_SEQUENCE,
                f"sequence {envelope.seq} is not newer than {self.last_seq}",
            )
        accepted = dict(self.idempotency_digests)
        accepted[envelope.idempotency_key] = envelope.digest()
        return replace(self, last_seq=envelope.seq, idempotency_digests=accepted)


@dataclass(frozen=True)
class ProtocolNegotiation:
    producer_protocol: str
    consumer_protocol: str
    outcome: str
    emitted_protocol: str


def negotiate_protocol(
    producer_protocol: str,
    consumer_protocol: str,
    *,
    requires_v2_semantics: bool = False,
    target_supports_v2: bool = True,
) -> ProtocolNegotiation:
    """Return an explicit mixed-version decision; never infer missing fields."""

    supported = {V1_PROTOCOL, V2_PROTOCOL}
    if producer_protocol not in supported or consumer_protocol not in supported:
        _fail(
            MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL,
            f"unsupported protocol pairing {producer_protocol!r} -> {consumer_protocol!r}",
        )
    if producer_protocol == V1_PROTOCOL and consumer_protocol == V1_PROTOCOL:
        return ProtocolNegotiation(producer_protocol, consumer_protocol, "SUPPORTED", V1_PROTOCOL)
    if producer_protocol == V2_PROTOCOL and consumer_protocol == V2_PROTOCOL:
        if not target_supports_v2:
            return ProtocolNegotiation(
                producer_protocol,
                consumer_protocol,
                "DOWNGRADE_UNSUPPORTED",
                V1_PROTOCOL,
            )
        return ProtocolNegotiation(producer_protocol, consumer_protocol, "SUPPORTED", V2_PROTOCOL)
    if producer_protocol == V1_PROTOCOL and consumer_protocol == V2_PROTOCOL:
        outcome = "REPLAN_REQUIRED" if requires_v2_semantics or not target_supports_v2 else "LOSSLESS_ADAPTER"
        return ProtocolNegotiation(producer_protocol, consumer_protocol, outcome, V2_PROTOCOL)
    if requires_v2_semantics:
        return ProtocolNegotiation(
            producer_protocol,
            consumer_protocol,
            "DOWNGRADE_UNSUPPORTED",
            V2_PROTOCOL,
        )
    return ProtocolNegotiation(producer_protocol, consumer_protocol, "LOSSLESS_ADAPTER", V1_PROTOCOL)


_V2_ADAPTER_REQUIRED_FIELDS = frozenset(
    {
        "protocol",
        "message_id",
        "run_id",
        "node_id",
        "seq",
        "correlation_id",
        "direction",
        "message_type",
        "producer",
        "recipient",
        "logical_contract",
        "attempt",
        "execution_identity",
        "source_manifest",
        "standards_profile",
        "payload",
        "provenance",
        "idempotency_key",
    }
)


def adapt_v1_to_v2(
    v1_payload: Mapping[str, Any],
    *,
    bound_v2_fields: Optional[Mapping[str, Any]] = None,
) -> V2MailboxEnvelope:
    """Adapt v1 only when a Controller supplies every v2 binding explicitly.

    The adapter carries the original v1 object under ``payload.legacy_v1``;
    it never derives identity, boundary, generation, source or fan-out fields
    from the legacy message.  A later persistence adapter can choose whether
    to retain that evidence, but the v2 envelope remains independently
    validated and digest-bound.
    """

    if not isinstance(v1_payload, Mapping) or v1_payload.get("protocol") != V1_PROTOCOL:
        _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "adapter input is not a v1 payload")
    if bound_v2_fields is None:
        _fail(
            MailboxV2ErrorCode.PROTOCOL_DOWNGRADE_UNSUPPORTED,
            "v2 identity, boundary and digest bindings must be supplied explicitly",
        )
    missing = sorted(_V2_ADAPTER_REQUIRED_FIELDS - set(bound_v2_fields))
    if missing:
        _fail(
            MailboxV2ErrorCode.PROTOCOL_DOWNGRADE_UNSUPPORTED,
            f"adapter cannot infer required v2 fields: {', '.join(missing)}",
        )
    candidate = copy.deepcopy(dict(bound_v2_fields))
    if candidate.get("protocol") != V2_PROTOCOL:
        _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "bound adapter target is not v2")
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "bound v2 payload must be an object")
    payload = copy.deepcopy(dict(payload))
    payload["legacy_v1"] = copy.deepcopy(dict(v1_payload))
    candidate["payload"] = payload
    candidate.pop("digest", None)
    candidate["digest"] = canonical_digest(candidate)
    return V2MailboxEnvelope.from_dict(candidate)


__all__ = [
    "adapt_v1_to_v2",
    "MailboxV2Cursor",
    "MailboxV2ErrorCode",
    "MailboxV2ValidationError",
    "ProtocolNegotiation",
    "V1_PROTOCOL",
    "V2MailboxEnvelope",
    "V2_PROTOCOL",
    "canonical_bytes",
    "canonical_digest",
    "get_v2_schema",
    "negotiate_protocol",
]
