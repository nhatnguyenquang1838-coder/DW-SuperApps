"""Campaign-scoped live certification facade with legacy W7 compatibility."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .certification_models import (
    CertificationCampaign,
    RuntimeCorrection,
    RuntimeFinding,
    SourceRevision,
    TestCase as CampaignTestCase,
    TestRun as CampaignTestRun,
)
from .certification_store import CertificationStore, CertificationStoreError
from .proving_workspace import (
    ExactCheckout,
    ProvingWorkspaceError,
    verify_distinct_workspace,
    verify_exact_checkout,
)


class LiveCertificationError(Exception):
    """Raised when a live certification operation violates its contract."""


# Compatibility-only W7 records. New campaign APIs use certification_models.
@dataclass
class TestCase:
    case_id: str
    scenario: str
    acceptance: str


@dataclass
class TestRunVerdict:
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


@dataclass
class RunMode:
    STANDARD_REAL_RUN = "STANDARD_REAL_RUN"
    DEEP_CERTIFICATION = "DEEP_CERTIFICATION"


@dataclass
class TestRun:
    run_id: str
    case_id: str
    scenario: str
    acceptance: str
    branch: str
    base_sha: str
    head_sha: str
    executor: str
    model: str
    pr_id: str = ""
    runtime_plan_ref: str = ""
    runtime_plan_digest: str = ""
    mode: str = RunMode.STANDARD_REAL_RUN
    verdict: str = TestRunVerdict.PENDING
    evidence: dict[str, Any] = field(default_factory=dict)
    expected: str = ""
    actual: str = ""
    branch_deleted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "scenario": self.scenario,
            "acceptance": self.acceptance,
            "branch": self.branch,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "executor": self.executor,
            "model": self.model,
            "pr_id": self.pr_id,
            "runtime_plan_ref": self.runtime_plan_ref,
            "runtime_plan_digest": self.runtime_plan_digest,
            "mode": self.mode,
            "verdict": self.verdict,
            "evidence": copy.deepcopy(self.evidence),
            "expected": self.expected,
            "actual": self.actual,
            "branch_deleted": self.branch_deleted,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TestRun":
        return cls(
            run_id=payload["run_id"],
            case_id=payload["case_id"],
            scenario=payload["scenario"],
            acceptance=payload["acceptance"],
            branch=payload["branch"],
            base_sha=payload["base_sha"],
            head_sha=payload["head_sha"],
            executor=payload["executor"],
            model=payload["model"],
            pr_id=payload.get("pr_id", ""),
            runtime_plan_ref=payload.get("runtime_plan_ref", ""),
            runtime_plan_digest=payload.get("runtime_plan_digest", ""),
            mode=payload.get("mode", RunMode.STANDARD_REAL_RUN),
            verdict=payload.get("verdict", TestRunVerdict.PENDING),
            evidence=copy.deepcopy(dict(payload.get("evidence", {}))),
            expected=payload.get("expected", ""),
            actual=payload.get("actual", ""),
            branch_deleted=bool(payload.get("branch_deleted", False)),
        )


class LiveCertificationHarness:
    """Campaign-scoped certification facade.

    The revised API persists canonical campaign events through
    :class:`CertificationStore`. The old keyword-only ``case=...`` API remains
    isolated as a compatibility reader/writer for v1 W7 JSONL records.
    """

    def __init__(self, store: str | Path | None = None) -> None:
        self._store = Path(store) if store else None
        self._event_store: CertificationStore | None = None
        self._legacy_store_mode = False
        self._runs: dict[str, TestRun] = {}
        self._branches: dict[str, str] = {}
        self._seen_terminal_verdicts: dict[str, str] = {}
        self._campaigns: dict[str, CertificationCampaign] = {}
        self._cases: dict[str, CampaignTestCase] = {}
        self._cert_runs: dict[str, CampaignTestRun] = {}
        self._findings: dict[str, RuntimeFinding] = {}
        self._corrections: dict[str, RuntimeCorrection] = {}
        self._campaign_branches: dict[tuple[str, str], str] = {}
        self._source_tuples: set[tuple[Any, ...]] = set()
        if self._store is not None and self._store.exists():
            self._detect_and_load_store()

    def _detect_and_load_store(self) -> None:
        store_path = self._store
        if store_path is None:
            return
        for line in store_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if "schema_version" in raw and "event_seq" in raw:
                self._event_store = CertificationStore(store_path)
                self._replay_events(self._event_store.replay())
            else:
                self._legacy_store_mode = True
                self._load_legacy_jsonl()
            return

    # --------------------------- revised campaign API ---------------------
    def _ensure_event_store(self) -> CertificationStore | None:
        if self._legacy_store_mode:
            raise LiveCertificationError(
                "legacy W7 JSONL store cannot accept revised campaign events"
            )
        if self._store is None:
            return None
        if self._event_store is None:
            self._event_store = CertificationStore(self._store)
        return self._event_store

    def _append_event(self, event_type: str, aggregate_id: str, payload: Mapping[str, object]) -> None:
        store = self._ensure_event_store()
        if store is not None:
            try:
                store.append(event_type, aggregate_id, payload)
            except CertificationStoreError as exc:
                raise LiveCertificationError(str(exc)) from exc

    def create_campaign(self, campaign: CertificationCampaign) -> CertificationCampaign:
        if not isinstance(campaign, CertificationCampaign):
            raise LiveCertificationError("CertificationCampaign required")
        if campaign.campaign_id in self._campaigns:
            raise LiveCertificationError(f"campaign {campaign.campaign_id!r} already exists")
        self._campaigns[campaign.campaign_id] = campaign
        for branch in (campaign.runtime_branch, campaign.proving_branch):
            key = ("nhatnguyenquang1838-coder/DW-SuperApps", branch)
            owner = self._campaign_branches.get(key)
            if owner is not None and owner != campaign.campaign_id:
                raise LiveCertificationError(f"branch {branch!r} already owned by campaign {owner!r}")
            self._campaign_branches[key] = campaign.campaign_id
        self._append_event("CAMPAIGN_CREATED", campaign.campaign_id, campaign.to_dict())
        return campaign

    def register_case(self, case: CampaignTestCase) -> CampaignTestCase:
        if not isinstance(case, CampaignTestCase):
            raise LiveCertificationError("versioned Campaign TestCase required")
        existing = self._cases.get(case.case_id)
        if existing is not None and existing != case:
            raise LiveCertificationError(f"case {case.case_id!r} already registered with another revision")
        self._cases[case.case_id] = case
        self._append_event("CASE_REGISTERED", case.case_id, case.to_dict())
        return case

    @staticmethod
    def _cert_run_from_dict(payload: Mapping[str, Any]) -> CampaignTestRun:
        return CampaignTestRun(
            run_id=payload["run_id"],
            campaign_id=payload["campaign_id"],
            case_id=payload["case_id"],
            case_revision=payload["case_revision"],
            runtime=SourceRevision(**payload["runtime"]),
            subject=SourceRevision(**payload["subject"]),
            gwc_sha=payload["gwc_sha"],
            runtime_plan_ref=payload["runtime_plan_ref"],
            runtime_plan_revision=payload["runtime_plan_revision"],
            runtime_plan_digest=payload["runtime_plan_digest"],
            executor=payload["executor"],
            model=payload["model"],
            verdict=payload["verdict"],
            evidence=payload.get("evidence", {}),
            legacy=bool(payload.get("legacy", False)),
        )

    @staticmethod
    def _campaign_from_dict(payload: Mapping[str, Any]) -> CertificationCampaign:
        return CertificationCampaign(**payload)

    @staticmethod
    def _case_from_dict(payload: Mapping[str, Any]) -> CampaignTestCase:
        return CampaignTestCase(
            case_id=payload["case_id"],
            revision=payload["revision"],
            scenario=payload["scenario"],
            acceptance=payload["acceptance"],
            declared_paths=tuple(payload["declared_paths"]),
        )

    def _replay_events(self, events: tuple[Any, ...]) -> None:
        for event in events:
            payload = event.payload
            if event.event_type == "CAMPAIGN_CREATED":
                campaign = self._campaign_from_dict(payload)
                self._campaigns[campaign.campaign_id] = campaign
                for branch in (campaign.runtime_branch, campaign.proving_branch):
                    self._campaign_branches[("nhatnguyenquang1838-coder/DW-SuperApps", branch)] = campaign.campaign_id
            elif event.event_type == "CASE_REGISTERED":
                case = self._case_from_dict(payload)
                self._cases[case.case_id] = case
            elif event.event_type in {"RUN_STARTED", "RUN_VERDICT_RECORDED"}:
                run = self._cert_run_from_dict(payload)
                self._cert_runs[run.run_id] = run
                self._campaign_branches[(run.subject.repository, run.subject.branch)] = run.campaign_id
                self._source_tuples.add(self._source_tuple(run))
            elif event.event_type == "FINDING_RECORDED":
                finding = RuntimeFinding(**dict(payload))
                self._findings[finding.finding_id] = finding
            elif event.event_type == "CORRECTION_RECORDED":
                correction = RuntimeCorrection(**dict(payload["correction"]))
                self._corrections[correction.correction_id] = correction
                for finding_id in correction.finding_ids:
                    finding = self._findings.get(finding_id)
                    if finding is not None:
                        self._findings[finding_id] = replace(
                            finding,
                            status="RESOLVED",
                            correction_id=correction.correction_id,
                            correction_sha=correction.runtime_sha,
                            regression_evidence=correction.regression_evidence,
                            successor_run_ids=correction.successor_run_ids,
                        )

    @staticmethod
    def _source_tuple(run: CampaignTestRun) -> tuple[Any, ...]:
        return (
            run.campaign_id,
            run.case_id,
            run.case_revision,
            run.runtime.repository,
            run.runtime.branch,
            run.runtime.start_sha,
            run.runtime.end_sha,
            run.subject.repository,
            run.subject.branch,
            run.subject.start_sha,
            run.subject.end_sha,
            run.gwc_sha,
            run.runtime_plan_ref,
            run.runtime_plan_revision,
            run.runtime_plan_digest,
        )

    def start_run(
        self,
        *,
        campaign_id: str | None = None,
        case_id: str | None = None,
        runtime: SourceRevision | None = None,
        subject: SourceRevision | None = None,
        gwc_sha: str | None = None,
        executor: str,
        model: str,
        run_id: str | None = None,
        runtime_plan_ref: str = "",
        runtime_plan_revision: str = "",
        runtime_plan_digest: str = "",
        # Compatibility-only W7 arguments:
        case: TestCase | None = None,
        branch: str | None = None,
        base_sha: str | None = None,
        head_sha: str | None = None,
        pr_id: str = "",
        mode: str = RunMode.STANDARD_REAL_RUN,
        runtime_checkout: ExactCheckout | None = None,
        subject_checkout: ExactCheckout | None = None,
        gwc_checkout: ExactCheckout | None = None,
        canonical_runtime_remote: str | None = None,
        canonical_subject_remote: str | None = None,
        canonical_gwc_remote: str | None = None,
    ) -> CampaignTestRun | TestRun:
        if campaign_id is None and runtime is None and subject is None:
            return self._start_legacy_run(
                case=case,
                branch=branch,
                base_sha=base_sha,
                head_sha=head_sha,
                executor=executor,
                model=model,
                pr_id=pr_id,
                runtime_plan_ref=runtime_plan_ref,
                runtime_plan_digest=runtime_plan_digest,
                mode=mode,
            )
        if campaign_id is None or case_id is None or runtime is None or subject is None or gwc_sha is None:
            raise LiveCertificationError("campaign, case, runtime, subject and GWC identity are required")
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise LiveCertificationError(f"campaign {campaign_id!r} not found")
        case_record = self._cases.get(case_id)
        if case_record is None:
            raise LiveCertificationError(f"versioned case {case_id!r} not found")
        if case_record.case_id != campaign.test_case_id or case_record.revision != campaign.test_case_revision:
            raise LiveCertificationError("case does not match campaign revision")
        if not executor or not model:
            raise LiveCertificationError("executor and model identity are required")
        if gwc_sha != campaign.gwc_sha:
            raise LiveCertificationError("GWC source binding does not match campaign")
        checkout_values = (runtime_checkout, subject_checkout, gwc_checkout)
        remote_values = (canonical_runtime_remote, canonical_subject_remote, canonical_gwc_remote)
        if any(value is not None for value in checkout_values + remote_values):
            if not all(value is not None for value in checkout_values + remote_values):
                raise LiveCertificationError("workspace binding requires all exact checkouts and canonical remotes")
            assert runtime_checkout is not None
            assert subject_checkout is not None
            assert gwc_checkout is not None
            assert canonical_runtime_remote is not None
            assert canonical_subject_remote is not None
            assert canonical_gwc_remote is not None
            try:
                verify_exact_checkout(runtime_checkout, canonical_runtime_remote)
                verify_exact_checkout(subject_checkout, canonical_subject_remote)
                verify_exact_checkout(gwc_checkout, canonical_gwc_remote)
                verify_distinct_workspace(runtime_checkout, subject_checkout)
            except ProvingWorkspaceError as exc:
                raise LiveCertificationError(f"workspace binding: {exc}") from exc
            if gwc_checkout.sha != gwc_sha:
                raise LiveCertificationError("workspace binding: GWC checkout SHA does not match campaign")
        branch_key = (subject.repository, subject.branch)
        owner = self._campaign_branches.get(branch_key)
        if owner is not None and owner != campaign_id:
            raise LiveCertificationError(f"branch {subject.branch!r} already owned by campaign {owner!r}")
        self._campaign_branches[branch_key] = campaign_id
        run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        if run_id in self._cert_runs:
            raise LiveCertificationError(f"duplicate run identity {run_id!r}")
        if not runtime_plan_ref or not runtime_plan_revision or not runtime_plan_digest:
            raise LiveCertificationError("runtime plan identity is required")
        run = CampaignTestRun(
            run_id=run_id,
            campaign_id=campaign_id,
            case_id=case_id,
            case_revision=case_record.revision,
            runtime=runtime,
            subject=subject,
            gwc_sha=gwc_sha,
            runtime_plan_ref=runtime_plan_ref,
            runtime_plan_revision=runtime_plan_revision,
            runtime_plan_digest=runtime_plan_digest,
            executor=executor,
            model=model,
            verdict="PENDING",
            evidence={},
        )
        source_tuple = self._source_tuple(run)
        if source_tuple in self._source_tuples:
            raise LiveCertificationError("duplicate exact source tuple")
        self._cert_runs[run_id] = run
        self._source_tuples.add(source_tuple)
        self._append_event("RUN_STARTED", run_id, run.to_dict())
        return run

    def record_finding(self, *, campaign_id: str, discovered_by_run_id: str, invariant_id: str,
                       severity: str, expected: str, actual: str,
                       reproduction_refs: tuple[str, ...], finding_id: str | None = None) -> RuntimeFinding:
        if campaign_id not in self._campaigns:
            raise LiveCertificationError(f"campaign {campaign_id!r} not found")
        if discovered_by_run_id not in self._cert_runs:
            raise LiveCertificationError(f"run {discovered_by_run_id!r} not found")
        finding = RuntimeFinding(
            finding_id=finding_id or f"finding-{uuid.uuid4().hex[:8]}",
            campaign_id=campaign_id,
            discovered_by_run_id=discovered_by_run_id,
            invariant_id=invariant_id,
            severity=severity,
            expected=expected,
            actual=actual,
            reproduction_refs=reproduction_refs,
            status="OPEN",
        )
        if finding.finding_id in self._findings:
            raise LiveCertificationError("duplicate finding identity")
        self._findings[finding.finding_id] = finding
        self._append_event("FINDING_RECORDED", finding.finding_id, finding.to_dict())
        return finding

    def record_correction(self, *, correction_id: str, finding_ids: tuple[str, ...], runtime_sha: str,
                          regression_evidence: tuple[str, ...], successor_run_ids: tuple[str, ...]) -> RuntimeCorrection:
        correction = RuntimeCorrection(
            correction_id=correction_id,
            finding_ids=finding_ids,
            runtime_sha=runtime_sha,
            regression_evidence=regression_evidence,
            successor_run_ids=successor_run_ids,
        )
        if correction_id in self._corrections:
            raise LiveCertificationError("duplicate correction identity")
        for finding_id in correction.finding_ids:
            finding = self._findings.get(finding_id)
            if finding is None:
                raise LiveCertificationError(f"finding {finding_id!r} not found")
            self._findings[finding_id] = replace(
                finding,
                status="RESOLVED",
                correction_id=correction.correction_id,
                correction_sha=correction.runtime_sha,
                regression_evidence=correction.regression_evidence,
                successor_run_ids=correction.successor_run_ids,
            )
        self._corrections[correction_id] = correction
        self._append_event(
            "CORRECTION_RECORDED",
            correction_id,
            {"correction": correction.to_dict(), "finding_ids": list(finding_ids)},
        )
        return correction

    def get_campaign(self, campaign_id: str) -> CertificationCampaign:
        try:
            return self._campaigns[campaign_id]
        except KeyError as exc:
            raise LiveCertificationError(f"campaign {campaign_id!r} not found") from exc

    def get_finding(self, finding_id: str) -> RuntimeFinding:
        try:
            return self._findings[finding_id]
        except KeyError as exc:
            raise LiveCertificationError(f"finding {finding_id!r} not found") from exc

    # ------------------------- revised verdict API ------------------------
    def record_verdict(
        self,
        run_id: str,
        verdict: str,
        evidence: Mapping[str, object],
        expected: str = "",
        actual: str = "",
        notion_data: dict[str, Any] | None = None,
    ) -> None:
        if run_id in self._cert_runs:
            if notion_data is not None:
                raise LiveCertificationError("Notion/Slack data must not be treated as machine truth")
            run = self._cert_runs[run_id]
            if run.verdict != "PENDING":
                raise LiveCertificationError("verdict is immutable after terminal record")
            if verdict not in {"PASS", "FAIL"}:
                raise LiveCertificationError("verdict must be exactly PASS or FAIL")
            if not evidence:
                raise LiveCertificationError("verdict requires exact refs/evidence")
            updated = replace(run, verdict=verdict, evidence=evidence)
            self._cert_runs[run_id] = updated
            self._append_event("RUN_VERDICT_RECORDED", run_id, updated.to_dict())
            return
        self._record_legacy_verdict(run_id, verdict, evidence, expected, actual, notion_data)

    # ------------------------- legacy W7 compatibility --------------------
    def _load_legacy_jsonl(self) -> None:
        if self._store is None or not self._store.exists():
            return
        for line in self._store.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            record_payload = {key: value for key, value in raw.items() if key != "_sha256"}
            record = TestRun.from_dict(record_payload)
            expected_sha = hashlib.sha256(json.dumps(record_payload, sort_keys=True).encode("utf-8")).hexdigest()
            stored_sha = raw.get("_sha256", "")
            if not stored_sha:
                raise LiveCertificationError(f"run {record.run_id!r} JSONL record has no _sha256 — invalid store state")
            if stored_sha != expected_sha:
                raise LiveCertificationError(f"run {record.run_id!r} JSONL record hash mismatch — tamper detected")
            if record.verdict not in (TestRunVerdict.PENDING, TestRunVerdict.PASS, TestRunVerdict.FAIL):
                raise LiveCertificationError(f"run {record.run_id!r} JSONL record has invalid persisted verdict {record.verdict!r}")
            if record.verdict != TestRunVerdict.PENDING:
                previous = self._seen_terminal_verdicts.get(record.run_id)
                if previous is not None and previous != record.verdict:
                    raise LiveCertificationError(f"run {record.run_id!r} JSONL contradictory terminal history: {previous} then {record.verdict}")
                self._seen_terminal_verdicts[record.run_id] = record.verdict
            self._runs[record.run_id] = record
            self._branches[record.branch] = record.run_id

    def _load(self) -> None:
        self._load_legacy_jsonl()

    def _append(self, run: TestRun) -> None:
        if self._store is None:
            return
        self._store.parent.mkdir(parents=True, exist_ok=True)
        core_payload = run.to_dict()
        record_sha256 = hashlib.sha256(json.dumps(core_payload, sort_keys=True).encode("utf-8")).hexdigest()
        payload = dict(core_payload)
        payload["_sha256"] = record_sha256
        with self._store.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _start_legacy_run(self, *, case: TestCase | None, branch: str | None, base_sha: str | None,
                          head_sha: str | None, executor: str, model: str, pr_id: str,
                          runtime_plan_ref: str, runtime_plan_digest: str, mode: str) -> TestRun:
        if case is None:
            raise LiveCertificationError("case identity required")
        if not executor:
            raise LiveCertificationError("executor identity required")
        if not model:
            raise LiveCertificationError("model identity required")
        if not branch or branch in self._branches:
            raise LiveCertificationError(f"branch {branch!r} already used" if branch else "branch required")
        run = TestRun(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            case_id=case.case_id,
            scenario=case.scenario,
            acceptance=case.acceptance,
            branch=branch,
            base_sha=base_sha or "",
            head_sha=head_sha or "",
            executor=executor,
            model=model,
            pr_id=pr_id,
            runtime_plan_ref=runtime_plan_ref,
            runtime_plan_digest=runtime_plan_digest,
            mode=mode,
        )
        self._runs[run.run_id] = run
        self._branches[branch] = run.run_id
        self._append(run)
        return run

    def _record_legacy_verdict(self, run_id: str, verdict: str, evidence: Mapping[str, object],
                               expected: str, actual: str, notion_data: dict[str, Any] | None) -> None:
        if notion_data is not None:
            raise LiveCertificationError("Notion/Slack data must not be treated as machine truth")
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        if not evidence:
            raise LiveCertificationError("verdict requires exact refs/evidence")
        if run.verdict != TestRunVerdict.PENDING:
            raise LiveCertificationError(f"verdict for run {run_id!r} is immutable (already recorded: {run.verdict})")
        if verdict not in (TestRunVerdict.PASS, TestRunVerdict.FAIL):
            raise LiveCertificationError(f"verdict for run {run_id!r} must be exactly PASS or FAIL; got {verdict!r}")
        run.verdict = verdict
        run.evidence = copy.deepcopy(dict(evidence))
        run.expected = expected
        run.actual = actual
        self._seen_terminal_verdicts[run_id] = verdict
        self._append(run)

    def get_run(self, run_id: str) -> CampaignTestRun | TestRun:
        if run_id in self._cert_runs:
            return self._cert_runs[run_id]
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        return copy.deepcopy(run)

    def delete_branch(self, *, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        raise LiveCertificationError(f"branch {run.branch!r} retained for certification run {run_id} (verdict {run.verdict})")

    def get_current_state(self, *, run_id: str) -> dict[str, Any]:
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        return {
            "run_id": run.run_id,
            "case_id": run.case_id,
            "verdict": run.verdict,
            "branch": run.branch,
            "head_sha": run.head_sha,
        }
