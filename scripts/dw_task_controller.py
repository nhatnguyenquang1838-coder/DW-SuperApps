#!/usr/bin/env python3
"""Generic TaskController MVP with an OpenAI-compatible GPT pilot adapter.

The controller owns plan compilation and report transitions.  It deliberately
does not own governance, Git, Slack, worker spawning, or merge authority.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_PATH = ROOT / "schemas" / "task-controller-plan.schema.json"
REPORT_SCHEMA_PATH = ROOT / "schemas" / "task-controller-report.schema.json"
AFTER_REPORT_VALUES = {"CONTINUE", "WAIT_CONTROLLER", "TERMINAL"}
REPORT_STATUS_VALUES = {"RUNNING", "DONE", "BLOCKED", "FAILED"}
DRIFT_VALUES = {"scope", "authority", "plan", "evidence", "material"}


class TaskControllerError(ValueError):
    """Raised when a plan, report, or controller transition is invalid."""


class ControllerModel(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return the model's raw response for a controller planning request."""


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskControllerError(f"unable to load schema {path}: {exc}") from exc
    if not isinstance(schema, dict):
        raise TaskControllerError(f"schema must be an object: {path}")
    return schema


def _validate_schema(payload: Mapping[str, Any], path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise TaskControllerError("jsonschema is required for TaskController contracts") from exc

    schema = _load_schema(path)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise TaskControllerError(f"invalid controller contract: {details}")


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerError(f"{key} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    title: str
    objective: str

    def __post_init__(self) -> None:
        for name, value in (("task_id", self.task_id), ("title", self.title), ("objective", self.objective)):
            if not isinstance(value, str) or not value.strip():
                raise TaskControllerError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class Subtask:
    id: str
    objective: str
    allowed_work: tuple[str, ...]
    expected_output: str
    report_requirement: str
    after_report: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Subtask":
        return cls(
            id=_text(payload, "id"),
            objective=_text(payload, "objective"),
            allowed_work=tuple(str(item).strip() for item in payload["allowedWork"]),
            expected_output=_text(payload, "expectedOutput"),
            report_requirement=_text(payload, "reportRequirement"),
            after_report=_text(payload, "afterReport"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "allowedWork": list(self.allowed_work),
            "expectedOutput": self.expected_output,
            "reportRequirement": self.report_requirement,
            "afterReport": self.after_report,
        }


@dataclass(frozen=True)
class TaskPlan:
    task_id: str
    title: str
    objective: str
    subtasks: tuple[Subtask, ...]
    schema_version: str = "1.0"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TaskPlan":
        _validate_schema(payload, PLAN_SCHEMA_PATH)
        subtasks = tuple(Subtask.from_payload(item) for item in payload["subtasks"])
        ids = [subtask.id for subtask in subtasks]
        if len(ids) != len(set(ids)):
            raise TaskControllerError("subtask ids must be unique")
        if len({subtask.after_report for subtask in subtasks}) == 0:
            raise TaskControllerError("plan must contain at least one report boundary")
        return cls(
            task_id=_text(payload, "taskId"),
            title=_text(payload, "title"),
            objective=_text(payload, "objective"),
            subtasks=subtasks,
            schema_version=_text(payload, "schemaVersion"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "taskId": self.task_id,
            "title": self.title,
            "objective": self.objective,
            "subtasks": [subtask.to_payload() for subtask in self.subtasks],
        }


@dataclass(frozen=True)
class ControllerReport:
    subtask_id: str
    status: str
    completed: str
    evidence: tuple[str, ...]
    next: str
    after: str
    finding_risk: str = ""
    drift: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ControllerReport":
        _validate_schema(payload, REPORT_SCHEMA_PATH)
        drift = tuple(payload.get("drift", []))
        unknown_drift = sorted(set(drift) - DRIFT_VALUES)
        if unknown_drift:
            raise TaskControllerError(f"unknown drift types: {', '.join(unknown_drift)}")
        return cls(
            subtask_id=_text(payload, "subtaskId"),
            status=_text(payload, "status"),
            completed=_text(payload, "completed"),
            evidence=tuple(str(item).strip() for item in payload["evidence"]),
            next=_text(payload, "next"),
            after=_text(payload, "after"),
            finding_risk=str(payload.get("findingRisk", "")).strip(),
            drift=drift,
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "subtaskId": self.subtask_id,
            "status": self.status,
            "completed": self.completed,
            "evidence": list(self.evidence),
            "next": self.next,
            "after": self.after,
        }
        if self.finding_risk:
            payload["findingRisk"] = self.finding_risk
        if self.drift:
            payload["drift"] = list(self.drift)
        return payload


@dataclass
class ControllerRun:
    run_id: str
    plan: TaskPlan
    current_index: int = 0
    status: str = "RUNNING"
    reports: list[ControllerReport] = field(default_factory=list)

    @property
    def current_subtask(self) -> Subtask | None:
        if self.current_index >= len(self.plan.subtasks):
            return None
        return self.plan.subtasks[self.current_index]


@dataclass(frozen=True)
class ControllerDecision:
    action: str
    reason: str
    run_status: str
    next_subtask_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "runStatus": self.run_status,
            "nextSubtaskId": self.next_subtask_id,
        }


@dataclass(frozen=True)
class ChatGPTPlanRequest:
    """Host-neutral request envelope for a ChatGPT controller turn."""

    task: TaskRequest
    system_prompt: str
    user_prompt: str
    response_schema: str = "schemas/task-controller-plan.schema.json"
    protocol: str = "dw-superapps.task-controller.plan.v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "task": {
                "id": self.task.task_id,
                "title": self.task.title,
                "objective": self.task.objective,
            },
            "systemPrompt": self.system_prompt,
            "userPrompt": self.user_prompt,
            "responseSchema": self.response_schema,
        }


def decode_json_object(response: str) -> dict[str, Any]:
    """Decode a JSON object from a model response, including fenced JSON."""
    if not isinstance(response, str) or not response.strip():
        raise TaskControllerError("controller model returned an empty response")
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise TaskControllerError("controller model response is not valid JSON") from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise TaskControllerError(f"controller model response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TaskControllerError("controller model response must be a JSON object")
    return payload


class OpenAICompatibleModel:
    """Small transport adapter for GPT or any OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        request_sender: Callable[[urllib.request.Request, float], bytes | str] | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise TaskControllerError("base_url and model are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.request_sender = request_sender

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        url = self.base_url
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            if self.request_sender is not None:
                raw = self.request_sender(request, self.timeout)
            else:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise TaskControllerError(f"controller model request failed: {exc}") from exc
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise TaskControllerError(f"controller model response has no chat content: {exc}") from exc
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise TaskControllerError("controller model returned empty chat content")
        return content


CONTROLLER_SYSTEM_PROMPT = """You are a generic TaskController for DW SuperApps.
Plan bounded execution for one Executor. Do not invent governance, approval,
merge, deployment, Slack, or worker-spawning authority. Return only one JSON
object matching the requested TaskController plan contract. Produce 3 to 5
meaningful subtasks, and keep each subtask independently reportable.
"""


class TaskController:
    """Model-agnostic controller engine for the GPT pilot and future models."""

    def __init__(
        self,
        model: ControllerModel | None,
        *,
        min_subtasks: int = 3,
        max_subtasks: int = 5,
    ) -> None:
        if not 3 <= min_subtasks <= max_subtasks <= 5:
            raise TaskControllerError("subtask bounds must be within 3..5")
        self.model = model
        self.min_subtasks = min_subtasks
        self.max_subtasks = max_subtasks

    def build_prompt(self, request: TaskRequest, context: Mapping[str, Any] | None = None) -> str:
        context_payload = dict(context or {})
        return json.dumps(
            {
                "task": {
                    "id": request.task_id,
                    "title": request.title,
                    "objective": request.objective,
                },
                "context": context_payload,
                "contract": {
                    "schemaVersion": "1.0",
                    "subtasks": f"exactly {self.min_subtasks} to {self.max_subtasks}",
                    "fields": [
                        "id",
                        "objective",
                        "allowedWork",
                        "expectedOutput",
                        "reportRequirement",
                        "afterReport",
                    ],
                    "afterReportValues": sorted(AFTER_REPORT_VALUES),
                },
            },
            indent=2,
            sort_keys=True,
        )

    def compile_plan_response(self, request: TaskRequest, response: str) -> TaskPlan:
        payload = decode_json_object(response)
        plan = TaskPlan.from_payload(payload)
        if not self.min_subtasks <= len(plan.subtasks) <= self.max_subtasks:
            raise TaskControllerError(
                f"plan must contain {self.min_subtasks}..{self.max_subtasks} subtasks"
            )
        if plan.task_id != request.task_id:
            raise TaskControllerError(
                f"plan taskId {plan.task_id!r} does not match request {request.task_id!r}"
            )
        return plan

    def plan(self, request: TaskRequest, context: Mapping[str, Any] | None = None) -> TaskPlan:
        if self.model is None:
            raise TaskControllerError(
                "no model is configured; use ChatGPTControllerBridge.prepare_plan_request()"
            )
        return self.compile_plan_response(
            request,
            self.model.complete(
                system_prompt=CONTROLLER_SYSTEM_PROMPT,
                user_prompt=self.build_prompt(request, context),
            ),
        )

    def start_run(self, plan: TaskPlan, *, run_id: str | None = None) -> ControllerRun:
        return ControllerRun(run_id=run_id or uuid.uuid4().hex, plan=plan)

    def resume(self, run: ControllerRun) -> None:
        if run.status != "WAIT_CONTROLLER":
            raise TaskControllerError(f"run is not waiting for controller: {run.status}")
        run.status = "RUNNING"

    def process_report(
        self,
        run: ControllerRun,
        report: ControllerReport | Mapping[str, Any],
    ) -> ControllerDecision:
        if run.status in {"COMPLETED", "TERMINAL", "BLOCKED", "FAILED"}:
            raise TaskControllerError(f"run is already terminal: {run.status}")
        if isinstance(report, Mapping):
            report = ControllerReport.from_payload(report)
        current = run.current_subtask
        if current is None:
            raise TaskControllerError("run has no active subtask")
        run.reports.append(report)

        if report.subtask_id != current.id:
            run.status = "WAIT_CONTROLLER"
            return ControllerDecision(
                "INTERCEPT",
                f"report belongs to {report.subtask_id}, expected {current.id}",
                run.status,
                current.id,
            )
        if report.after not in AFTER_REPORT_VALUES:
            raise TaskControllerError(f"invalid after value: {report.after}")
        if report.after != current.after_report:
            run.status = "WAIT_CONTROLLER"
            return ControllerDecision(
                "INTERCEPT",
                f"report boundary {report.after} conflicts with plan {current.after_report}",
                run.status,
                current.id,
            )
        if report.drift:
            run.status = "WAIT_CONTROLLER"
            return ControllerDecision(
                "INTERCEPT",
                "material drift reported: " + ", ".join(report.drift),
                run.status,
                current.id,
            )
        if report.status in {"BLOCKED", "FAILED"}:
            run.status = report.status
            return ControllerDecision(
                "TERMINAL",
                f"executor reported {report.status.lower()}",
                run.status,
                current.id,
            )
        if report.after == "WAIT_CONTROLLER":
            run.status = "WAIT_CONTROLLER"
            return ControllerDecision("WAIT_CONTROLLER", "controller review required", run.status, current.id)
        if report.after == "TERMINAL":
            run.status = "TERMINAL"
            return ControllerDecision("TERMINAL", "contracted run termination", run.status)

        run.current_index += 1
        next_subtask = run.current_subtask
        if next_subtask is None:
            run.status = "COMPLETED"
            return ControllerDecision("TERMINAL", "all contracted subtasks completed", run.status)
        return ControllerDecision("CONTINUE", "release next contracted subtask", run.status, next_subtask.id)


class GPTTaskController(TaskController):
    """Named pilot façade; the controller contract remains model-agnostic."""


class ChatGPTControllerBridge:
    """Bridge the engine to a ChatGPT host without calling the ChatGPT UI.

    A ChatGPT host calls ``prepare_plan_request``, sends the returned prompt in
    its own model turn, and passes the model's raw response to
    ``compile_plan_response``.  This keeps the runtime deterministic and avoids
    pretending that a local process can access a ChatGPT conversation directly.
    """

    def __init__(self, *, min_subtasks: int = 3, max_subtasks: int = 5) -> None:
        self.engine = TaskController(
            None,
            min_subtasks=min_subtasks,
            max_subtasks=max_subtasks,
        )

    def prepare_plan_request(
        self,
        request: TaskRequest,
        context: Mapping[str, Any] | None = None,
    ) -> ChatGPTPlanRequest:
        return ChatGPTPlanRequest(
            task=request,
            system_prompt=CONTROLLER_SYSTEM_PROMPT,
            user_prompt=self.engine.build_prompt(request, context),
        )

    def compile_plan_response(self, request: TaskRequest, response: str) -> TaskPlan:
        return self.engine.compile_plan_response(request, response)

    def start_run(self, plan: TaskPlan, *, run_id: str | None = None) -> ControllerRun:
        return self.engine.start_run(plan, run_id=run_id)

    def resume(self, run: ControllerRun) -> None:
        self.engine.resume(run)

    def process_report(
        self,
        run: ControllerRun,
        report: ControllerReport | Mapping[str, Any],
    ) -> ControllerDecision:
        return self.engine.process_report(run, report)


class ChatGPTTaskController(ChatGPTControllerBridge):
    """Convenience name for the ChatGPT-hosted controller pilot."""


class _StaticResponseModel:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dw task-controller")
    plan_parser = parser.add_subparsers(dest="command", required=True).add_parser(
        "plan", help="compile a bounded TaskController plan"
    )
    plan_parser.add_argument("--task-id", required=True)
    plan_parser.add_argument("--title", required=True)
    plan_parser.add_argument("--objective", required=True)
    plan_parser.add_argument("--context-json", default="{}")
    plan_parser.add_argument("--response-file", type=Path)
    plan_parser.add_argument("--base-url", default=os.environ.get("DW_CONTROLLER_BASE_URL", ""))
    plan_parser.add_argument("--model", default=os.environ.get("DW_CONTROLLER_MODEL", ""))
    plan_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_cli().parse_args(argv)
        if args.command != "plan":
            raise TaskControllerError(f"unknown command: {args.command}")
        try:
            context = json.loads(args.context_json)
        except json.JSONDecodeError as exc:
            raise TaskControllerError(f"--context-json must be valid JSON: {exc}") from exc
        if not isinstance(context, dict):
            raise TaskControllerError("--context-json must be a JSON object")
        if args.response_file:
            model: ControllerModel = _StaticResponseModel(
                args.response_file.read_text(encoding="utf-8")
            )
        else:
            if not args.base_url or not args.model:
                raise TaskControllerError(
                    "live planning requires --base-url/--model or DW_CONTROLLER_BASE_URL/DW_CONTROLLER_MODEL"
                )
            model = OpenAICompatibleModel(
                base_url=args.base_url,
                api_key=os.environ.get(args.api_key_env, ""),
                model=args.model,
            )
        controller = GPTTaskController(model)
        plan = controller.plan(
            TaskRequest(args.task_id, args.title, args.objective),
            context,
        )
        print(json.dumps(plan.to_payload(), indent=2, sort_keys=True))
        return 0
    except (TaskControllerError, OSError, json.JSONDecodeError) as exc:
        print(f"dw-task-controller: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
