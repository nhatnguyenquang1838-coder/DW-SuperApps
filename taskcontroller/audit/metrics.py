"""Bounded operational metrics for TaskController v2 observability.

The registry is an in-process projection primitive. It intentionally does not
persist prompts, transcripts, execution identities, or arbitrary provider/error
text. Callers may add it at an adapter boundary without changing the v1 audit
schema or mailbox protocol.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from threading import RLock


class MetricName(str, Enum):
    """Stable, low-cardinality metric names exposed by this module."""

    DISPATCH_TOTAL = "taskcontroller_dispatch_total"
    MAILBOX_READ_TOTAL = "taskcontroller_mailbox_read_total"
    DISPATCH_LATENCY_MS = "taskcontroller_dispatch_latency_ms"
    MAILBOX_READ_LATENCY_MS = "taskcontroller_mailbox_read_latency_ms"
    CHILD_COUNT = "taskcontroller_child_count"
    REVIEW_TOTAL = "taskcontroller_review_total"
    CONFLICT_TOTAL = "taskcontroller_conflict_total"
    CONFLICT_RATE = "taskcontroller_conflict_rate"
    RETRY_TOTAL = "taskcontroller_retry_total"
    TAKEOVER_TOTAL = "taskcontroller_takeover_total"
    STALE_REJECTION_TOTAL = "taskcontroller_stale_rejection_total"
    PROTOCOL_FAILURE_TOTAL = "taskcontroller_protocol_failure_total"

    @property
    def is_counter(self) -> bool:
        return self.value in _COUNTER_NAMES

    @property
    def is_observation(self) -> bool:
        return self.value in _OBSERVATION_NAMES


_COUNTER_NAMES = frozenset(
    {
        MetricName.DISPATCH_TOTAL.value,
        MetricName.MAILBOX_READ_TOTAL.value,
        MetricName.REVIEW_TOTAL.value,
        MetricName.CONFLICT_TOTAL.value,
        MetricName.RETRY_TOTAL.value,
        MetricName.TAKEOVER_TOTAL.value,
        MetricName.STALE_REJECTION_TOTAL.value,
        MetricName.PROTOCOL_FAILURE_TOTAL.value,
    }
)

_OBSERVATION_NAMES = frozenset(
    {
        MetricName.DISPATCH_LATENCY_MS.value,
        MetricName.MAILBOX_READ_LATENCY_MS.value,
        MetricName.CHILD_COUNT.value,
    }
)

_ALLOWED_LABEL_VALUES = {
    "protocol": frozenset({"v1", "v2"}),
    "lane": frozenset(
        {
            "audit",
            "controller",
            "cross_review",
            "executor",
            "fanout",
            "mailbox",
            "wakeup",
        }
    ),
    "execution_class": frozenset({"atomic", "complex", "cross_review", "review"}),
    "outcome": frozenset({"accepted", "blocked", "failed", "recovered", "rejected"}),
    "reason": frozenset(
        {"cancelled", "conflict", "duplicate", "lease_expired", "stale_generation", "timeout", "transport"}
    ),
    "error_code": frozenset(
        {
            "BOUNDARY_MISMATCH",
            "CONTRACT_MISMATCH",
            "DIGEST_MISMATCH",
            "INVALID_SEQUENCE",
            "MANIFEST_VERSION_MISMATCH",
            "PROTOCOL_DOWNGRADE_UNSUPPORTED",
            "SCHEMA_INVALID",
            "STANDARDS_RESOLUTION_BLOCKED",
            "STALE_GENERATION",
            "UNSUPPORTED_PROTOCOL",
            "WAKEUP_DELIVERY_BLOCKED",
        }
    ),
}
_MAX_LABELS = 4
_SCHEMA = "taskcontroller.operational-metrics/v1"


class MetricsError(ValueError):
    """Fail-closed validation error for metric inputs."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _normalize_labels(labels: Mapping[str, str] | None, *, error_code: str | None = None) -> tuple[tuple[str, str], ...]:
    if labels is None:
        values: dict[object, object] = {}
    elif isinstance(labels, Mapping):
        values = {}
        for key, value in labels.items():
            values[key] = value
    else:
        raise MetricsError("LABELS_INVALID", "labels must be a mapping")

    if error_code is not None:
        if "error_code" in values:
            raise MetricsError("LABEL_DUPLICATE", "protocol failure supplies error_code")
        values["error_code"] = error_code

    if len(values) > _MAX_LABELS:
        raise MetricsError("LABEL_LIMIT_EXCEEDED", "too many metric labels")

    normalized: list[tuple[str, str]] = []
    for key, value in values.items():
        if not isinstance(key, str) or key not in _ALLOWED_LABEL_VALUES:
            raise MetricsError("LABEL_NOT_ALLOWED", "metric label name is not stable")
        allowed_values = _ALLOWED_LABEL_VALUES[key]
        if not isinstance(value, str) or value not in allowed_values:
            raise MetricsError("LABEL_VALUE_NOT_ALLOWED", f"unsupported value for {key}")
        normalized.append((key, value))
    return tuple(sorted(normalized))


def _require_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:  # bool is deliberately not an integer input.
        raise MetricsError("VALUE_INVALID", f"{field} must be a non-negative integer")
    return value


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise MetricsError("VALUE_INVALID", f"{field} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class _CounterPoint:
    name: MetricName
    labels: tuple[tuple[str, str], ...]
    value: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "labels": dict(self.labels),
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class _ObservationPoint:
    name: MetricName
    labels: tuple[tuple[str, str], ...]
    count: int
    total: int
    maximum: int

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name.value,
            "labels": dict(self.labels),
            "count": self.count,
        }
        if self.name in {
            MetricName.DISPATCH_LATENCY_MS,
            MetricName.MAILBOX_READ_LATENCY_MS,
        }:
            payload.update({"sum_ms": self.total, "max_ms": self.maximum})
        else:
            payload.update({"sum": self.total, "max": self.maximum})
        return payload


@dataclass(frozen=True, slots=True)
class _ConflictRatePoint:
    labels: tuple[tuple[str, str], ...]
    numerator: int
    denominator: int

    def to_dict(self) -> dict[str, object]:
        basis_points = (self.numerator * 10_000) // self.denominator if self.denominator else 0
        return {
            "name": MetricName.CONFLICT_RATE.value,
            "labels": dict(self.labels),
            "numerator": self.numerator,
            "denominator": self.denominator,
            "basis_points": basis_points,
        }


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Immutable point-in-time metrics projection."""

    counters: tuple[_CounterPoint, ...]
    observations: tuple[_ObservationPoint, ...]
    rates: tuple[_ConflictRatePoint, ...]

    def conflict_rate(self, labels: Mapping[str, str] | None = None) -> dict[str, object]:
        normalized = _normalize_labels(labels)
        for point in self.rates:
            if point.labels == normalized:
                return point.to_dict()
        return _ConflictRatePoint(normalized, 0, 0).to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "counters": [point.to_dict() for point in self.counters],
            "observations": [point.to_dict() for point in self.observations],
            "rates": [point.to_dict() for point in self.rates],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class OperationalMetrics:
    """Thread-safe bounded registry for TaskController operational metrics."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counters: dict[tuple[MetricName, tuple[tuple[str, str], ...]], int] = {}
        self._observations: dict[
            tuple[MetricName, tuple[tuple[str, str], ...]], tuple[int, int, int]
        ] = {}
        self._reviews: dict[tuple[tuple[str, str], ...], tuple[int, int]] = {}

    def _increment(self, name: MetricName, labels: tuple[tuple[str, str], ...]) -> None:
        key = (name, labels)
        self._counters[key] = self._counters.get(key, 0) + 1

    def _observe(
        self,
        name: MetricName,
        labels: tuple[tuple[str, str], ...],
        value: int,
    ) -> None:
        key = (name, labels)
        count, total, maximum = self._observations.get(key, (0, 0, 0))
        self._observations[key] = (count + 1, total + value, max(maximum, value))

    def record_dispatch(
        self,
        *,
        latency_ms: int,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        value = _require_nonnegative_int(latency_ms, "latency_ms")
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.DISPATCH_TOTAL, normalized)
            self._observe(MetricName.DISPATCH_LATENCY_MS, normalized, value)

    def record_mailbox_read(
        self,
        *,
        latency_ms: int,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        value = _require_nonnegative_int(latency_ms, "latency_ms")
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.MAILBOX_READ_TOTAL, normalized)
            self._observe(MetricName.MAILBOX_READ_LATENCY_MS, normalized, value)

    def record_child_count(
        self,
        child_count: int,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        value = _require_nonnegative_int(child_count, "child_count")
        normalized = _normalize_labels(labels)
        with self._lock:
            self._observe(MetricName.CHILD_COUNT, normalized, value)

    def record_review(
        self,
        *,
        conflicted: bool,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        is_conflicted = _require_bool(conflicted, "conflicted")
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.REVIEW_TOTAL, normalized)
            if is_conflicted:
                self._increment(MetricName.CONFLICT_TOTAL, normalized)
            reviews, conflicts = self._reviews.get(normalized, (0, 0))
            self._reviews[normalized] = (
                reviews + 1,
                conflicts + (1 if is_conflicted else 0),
            )

    def record_retry(self, *, labels: Mapping[str, str] | None = None) -> None:
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.RETRY_TOTAL, normalized)

    def record_takeover(self, *, labels: Mapping[str, str] | None = None) -> None:
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.TAKEOVER_TOTAL, normalized)

    def record_stale_rejection(self, *, labels: Mapping[str, str] | None = None) -> None:
        normalized = _normalize_labels(labels)
        with self._lock:
            self._increment(MetricName.STALE_REJECTION_TOTAL, normalized)

    def record_protocol_failure(
        self,
        error_code: str,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(error_code, str) or error_code not in _ALLOWED_LABEL_VALUES["error_code"]:
            raise MetricsError("ERROR_CODE_NOT_ALLOWED", "protocol error code is not stable")
        normalized = _normalize_labels(labels, error_code=error_code)
        with self._lock:
            self._increment(MetricName.PROTOCOL_FAILURE_TOTAL, normalized)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            counters = tuple(
                _CounterPoint(name, labels, value)
                for (name, labels), value in sorted(
                    self._counters.items(),
                    key=lambda item: (item[0][0].value, item[0][1]),
                )
            )
            observations = tuple(
                _ObservationPoint(name, labels, count, total, maximum)
                for (name, labels), (count, total, maximum) in sorted(
                    self._observations.items(),
                    key=lambda item: (item[0][0].value, item[0][1]),
                )
            )
            rates = tuple(
                _ConflictRatePoint(labels, conflicts, reviews)
                for labels, (reviews, conflicts) in sorted(
                    self._reviews.items(), key=lambda item: item[0]
                )
            )
            return MetricsSnapshot(counters, observations, rates)


__all__ = ["MetricName", "MetricsError", "MetricsSnapshot", "OperationalMetrics"]
