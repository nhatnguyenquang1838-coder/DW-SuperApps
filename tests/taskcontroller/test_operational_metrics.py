"""TC-MBX-902: bounded operational metrics contract."""

from __future__ import annotations

import json
from math import nan

import pytest

from taskcontroller.audit.metrics import (
    MetricName,
    MetricsError,
    OperationalMetrics,
)


EXPECTED_COUNTERS = {
    "taskcontroller_dispatch_total",
    "taskcontroller_mailbox_read_total",
    "taskcontroller_review_total",
    "taskcontroller_conflict_total",
    "taskcontroller_retry_total",
    "taskcontroller_takeover_total",
    "taskcontroller_stale_rejection_total",
    "taskcontroller_protocol_failure_total",
}

EXPECTED_OBSERVATIONS = {
    "taskcontroller_dispatch_latency_ms",
    "taskcontroller_mailbox_read_latency_ms",
    "taskcontroller_child_count",
}


V2_CONTROLLER = {"protocol": "v2", "lane": "controller"}
V2_MAILBOX = {"protocol": "v2", "lane": "mailbox"}
V2_REVIEW = {"protocol": "v2", "execution_class": "review"}


def _metric_value(payload: dict, name: str, labels: dict) -> dict:
    for item in payload["counters"] + payload["observations"]:
        if item["name"] == name and item["labels"] == labels:
            return item
    raise AssertionError(f"metric not found: {name} {labels}")


def _rate_value(payload: dict, labels: dict) -> dict:
    for item in payload["rates"]:
        if item["name"] == "taskcontroller_conflict_rate" and item["labels"] == labels:
            return item
    raise AssertionError(f"conflict rate not found: {labels}")


def test_catalog_exposes_stable_operational_metric_names() -> None:
    assert {
        metric.value
        for metric in MetricName
        if metric.is_counter
    } == EXPECTED_COUNTERS
    assert {
        metric.value
        for metric in MetricName
        if metric.is_observation
    } == EXPECTED_OBSERVATIONS
    assert MetricName.CONFLICT_RATE.value == "taskcontroller_conflict_rate"


def test_records_dispatch_read_latency_children_and_operational_counters() -> None:
    metrics = OperationalMetrics()
    metrics.record_dispatch(latency_ms=12, labels=V2_CONTROLLER)
    metrics.record_mailbox_read(latency_ms=7, labels=V2_MAILBOX)
    metrics.record_child_count(3, labels=V2_REVIEW)
    metrics.record_review(conflicted=True, labels=V2_REVIEW)
    metrics.record_review(conflicted=False, labels=V2_REVIEW)
    metrics.record_retry(labels={"protocol": "v2", "reason": "timeout"})
    metrics.record_takeover(labels={"protocol": "v2", "reason": "lease_expired"})
    metrics.record_stale_rejection(
        labels={"protocol": "v2", "reason": "stale_generation"}
    )
    metrics.record_protocol_failure(
        "SCHEMA_INVALID", labels={"protocol": "v2", "lane": "mailbox"}
    )

    payload = metrics.snapshot().to_dict()
    assert _metric_value(
        payload, "taskcontroller_dispatch_total", V2_CONTROLLER
    )["value"] == 1
    assert _metric_value(
        payload, "taskcontroller_mailbox_read_total", V2_MAILBOX
    )["value"] == 1
    assert _metric_value(
        payload, "taskcontroller_dispatch_latency_ms", V2_CONTROLLER
    ) == {
        "name": "taskcontroller_dispatch_latency_ms",
        "labels": V2_CONTROLLER,
        "count": 1,
        "sum_ms": 12,
        "max_ms": 12,
    }
    assert _metric_value(
        payload, "taskcontroller_mailbox_read_latency_ms", V2_MAILBOX
    )["sum_ms"] == 7
    assert _metric_value(
        payload, "taskcontroller_child_count", V2_REVIEW
    ) == {
        "name": "taskcontroller_child_count",
        "labels": V2_REVIEW,
        "count": 1,
        "sum": 3,
        "max": 3,
    }
    assert _metric_value(
        payload, "taskcontroller_review_total", V2_REVIEW
    )["value"] == 2
    assert _metric_value(
        payload, "taskcontroller_conflict_total", V2_REVIEW
    )["value"] == 1
    assert _metric_value(
        payload,
        "taskcontroller_retry_total",
        {"protocol": "v2", "reason": "timeout"},
    )["value"] == 1
    assert _metric_value(
        payload,
        "taskcontroller_takeover_total",
        {"protocol": "v2", "reason": "lease_expired"},
    )["value"] == 1
    assert _metric_value(
        payload,
        "taskcontroller_stale_rejection_total",
        {"protocol": "v2", "reason": "stale_generation"},
    )["value"] == 1
    assert _metric_value(
        payload,
        "taskcontroller_protocol_failure_total",
        {"protocol": "v2", "lane": "mailbox", "error_code": "SCHEMA_INVALID"},
    )["value"] == 1


def test_conflict_rate_is_deterministic_and_preserves_numerator_denominator() -> None:
    metrics = OperationalMetrics()
    for conflicted in (True, False, False, True):
        metrics.record_review(conflicted=conflicted, labels=V2_REVIEW)

    rate = _rate_value(metrics.snapshot().to_dict(), V2_REVIEW)
    assert rate == {
        "name": "taskcontroller_conflict_rate",
        "labels": V2_REVIEW,
        "numerator": 2,
        "denominator": 4,
        "basis_points": 5000,
    }


def test_empty_review_set_has_zero_conflict_rate() -> None:
    metrics = OperationalMetrics()
    assert metrics.snapshot().conflict_rate(V2_REVIEW) == {
        "name": "taskcontroller_conflict_rate",
        "labels": V2_REVIEW,
        "numerator": 0,
        "denominator": 0,
        "basis_points": 0,
    }


def test_export_is_deterministic_and_contains_no_task_body() -> None:
    first = OperationalMetrics()
    first.record_dispatch(latency_ms=12, labels={"lane": "controller", "protocol": "v2"})
    first.record_review(conflicted=True, labels=V2_REVIEW)
    first.record_protocol_failure("SCHEMA_INVALID", labels={"protocol": "v2"})

    second = OperationalMetrics()
    second.record_protocol_failure("SCHEMA_INVALID", labels={"protocol": "v2"})
    second.record_review(conflicted=True, labels={"execution_class": "review", "protocol": "v2"})
    second.record_dispatch(latency_ms=12, labels=V2_CONTROLLER)

    assert first.snapshot().to_json() == second.snapshot().to_json()
    serialized = first.snapshot().to_json()
    assert json.loads(serialized)["schema"] == "taskcontroller.operational-metrics/v1"
    assert "prompt" not in serialized.lower()
    assert "transcript" not in serialized.lower()
    assert "raw task body" not in serialized.lower()


@pytest.mark.parametrize(
    ("labels", "error_code"),
    [
        ({"prompt": "secret"}, "LABEL_NOT_ALLOWED"),
        ({"transcript": "secret"}, "LABEL_NOT_ALLOWED"),
        ({"run_id": "run-902"}, "LABEL_NOT_ALLOWED"),
        ({"node_id": "node-root"}, "LABEL_NOT_ALLOWED"),
        ({"child_id": "child-1"}, "LABEL_NOT_ALLOWED"),
        ({"message_id": "message-1"}, "LABEL_NOT_ALLOWED"),
        ({"lane": "run-902"}, "LABEL_VALUE_NOT_ALLOWED"),
        ({"custom": "stable?"}, "LABEL_NOT_ALLOWED"),
    ],
)
def test_rejects_high_cardinality_or_unknown_labels(labels: dict, error_code: str) -> None:
    with pytest.raises(MetricsError, match=error_code):
        OperationalMetrics().record_dispatch(latency_ms=1, labels=labels)


def test_rejects_invalid_numeric_observations() -> None:
    metrics = OperationalMetrics()
    with pytest.raises(MetricsError, match="VALUE_INVALID"):
        metrics.record_dispatch(latency_ms=-1, labels=V2_CONTROLLER)
    with pytest.raises(MetricsError, match="VALUE_INVALID"):
        metrics.record_dispatch(latency_ms=nan, labels=V2_CONTROLLER)
    with pytest.raises(MetricsError, match="VALUE_INVALID"):
        metrics.record_child_count(-1, labels=V2_REVIEW)
    with pytest.raises(MetricsError, match="VALUE_INVALID"):
        metrics.record_child_count(1.5, labels=V2_REVIEW)
    with pytest.raises(MetricsError, match="VALUE_INVALID"):
        metrics.record_review(conflicted="yes", labels=V2_REVIEW)


def test_rejects_unbounded_protocol_failure_codes() -> None:
    with pytest.raises(MetricsError, match="ERROR_CODE_NOT_ALLOWED"):
        OperationalMetrics().record_protocol_failure(
            "raw prompt text", labels={"protocol": "v2"}
        )


def test_metric_snapshot_is_immutable() -> None:
    metrics = OperationalMetrics()
    metrics.record_dispatch(latency_ms=2, labels=V2_CONTROLLER)
    snapshot = metrics.snapshot()
    with pytest.raises(AttributeError):
        snapshot.counters = ()
    metrics.record_dispatch(latency_ms=3, labels=V2_CONTROLLER)
    assert _metric_value(
        snapshot.to_dict(), "taskcontroller_dispatch_total", V2_CONTROLLER
    )["value"] == 1


@pytest.mark.parametrize(
    "metric",
    [
        MetricName.DISPATCH_TOTAL,
        MetricName.MAILBOX_READ_TOTAL,
        MetricName.REVIEW_TOTAL,
        MetricName.CONFLICT_TOTAL,
        MetricName.RETRY_TOTAL,
        MetricName.TAKEOVER_TOTAL,
        MetricName.STALE_REJECTION_TOTAL,
        MetricName.PROTOCOL_FAILURE_TOTAL,
    ],
)
def test_metric_enum_values_are_nonempty_and_unique(metric: MetricName) -> None:
    assert metric.value
    assert list(MetricName).count(metric) == 1
