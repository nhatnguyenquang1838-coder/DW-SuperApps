from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dw_task_controller import (  # noqa: E402
    ChatGPTControllerBridge,
    ControllerReport,
    GPTTaskController,
    OpenAICompatibleModel,
    TaskController,
    TaskControllerError,
    TaskPlan,
    TaskRequest,
)


def plan_payload(task_id: str = "TASK-1") -> dict:
    return {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "title": "Generic controller pilot",
        "objective": "Compile and execute a bounded controller plan",
        "subtasks": [
            {
                "id": "S1",
                "objective": "Inspect the bounded target",
                "allowedWork": ["read repository files"],
                "expectedOutput": "target inventory",
                "reportRequirement": "report verified paths and risks",
                "afterReport": "CONTINUE",
            },
            {
                "id": "S2",
                "objective": "Implement the bounded change",
                "allowedWork": ["edit target files", "run focused tests"],
                "expectedOutput": "implementation and focused test result",
                "reportRequirement": "report changed files and commands",
                "afterReport": "CONTINUE",
            },
            {
                "id": "S3",
                "objective": "Review the result",
                "allowedWork": ["run validation", "summarize residual risk"],
                "expectedOutput": "validation evidence",
                "reportRequirement": "report exact validation evidence",
                "afterReport": "TERMINAL",
            },
        ],
    }


def report_payload(subtask_id: str, after: str = "CONTINUE", *, drift: list[str] | None = None) -> dict:
    payload = {
        "subtaskId": subtask_id,
        "status": "DONE",
        "completed": f"completed {subtask_id}",
        "evidence": [f"evidence for {subtask_id}"],
        "next": "continue with the contracted next step",
        "after": after,
    }
    if drift:
        payload["drift"] = drift
    return payload


class FakeModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class TaskControllerTests(unittest.TestCase):
    def test_plan_is_model_agnostic_and_accepts_fenced_json(self) -> None:
        model = FakeModel("```json\n" + json.dumps(plan_payload()) + "\n```")
        controller = TaskController(model)
        plan = controller.plan(TaskRequest("TASK-1", "Pilot", "Run the pilot"))

        self.assertIsInstance(plan, TaskPlan)
        self.assertEqual(3, len(plan.subtasks))
        self.assertEqual(1, len(model.calls))
        self.assertNotIn("gwc", model.calls[0][0].lower())

    def test_chatgpt_bridge_emits_host_request_and_compiles_response(self) -> None:
        bridge = ChatGPTControllerBridge()
        request = TaskRequest("TASK-1", "Pilot", "Run the pilot")
        envelope = bridge.prepare_plan_request(request, {"repository": "DW-SuperApps"})
        payload = envelope.to_payload()

        self.assertEqual("dw-superapps.task-controller.plan.v1", payload["protocol"])
        self.assertEqual("schemas/task-controller-plan.schema.json", payload["responseSchema"])
        self.assertIn("JSON", payload["systemPrompt"])
        plan = bridge.compile_plan_response(request, json.dumps(plan_payload()))
        run = bridge.start_run(plan, run_id="run-1")
        self.assertEqual("S1", run.current_subtask.id)

    def test_run_advances_only_at_contracted_boundaries(self) -> None:
        controller = GPTTaskController(FakeModel(json.dumps(plan_payload())))
        plan = controller.plan(TaskRequest("TASK-1", "Pilot", "Run the pilot"))
        run = controller.start_run(plan, run_id="run-1")

        first = controller.process_report(run, report_payload("S1"))
        second = controller.process_report(run, report_payload("S2"))
        terminal = controller.process_report(run, report_payload("S3", "TERMINAL"))

        self.assertEqual("CONTINUE", first.action)
        self.assertEqual("S2", first.next_subtask_id)
        self.assertEqual("CONTINUE", second.action)
        self.assertEqual("S3", second.next_subtask_id)
        self.assertEqual("TERMINAL", terminal.action)
        self.assertEqual("TERMINAL", run.status)

    def test_drift_intercepts_before_next_subtask(self) -> None:
        controller = GPTTaskController(FakeModel(json.dumps(plan_payload())))
        run = controller.start_run(controller.plan(TaskRequest("TASK-1", "Pilot", "Run the pilot")))

        decision = controller.process_report(run, report_payload("S1", drift=["scope"]))

        self.assertEqual("INTERCEPT", decision.action)
        self.assertEqual("WAIT_CONTROLLER", run.status)
        self.assertEqual("S1", run.current_subtask.id)

    def test_invalid_plan_is_rejected(self) -> None:
        invalid = plan_payload()
        invalid["subtasks"] = invalid["subtasks"][:2]
        controller = TaskController(FakeModel(json.dumps(invalid)))

        with self.assertRaises(TaskControllerError):
            controller.plan(TaskRequest("TASK-1", "Pilot", "Run the pilot"))

    def test_openai_compatible_adapter_is_transport_injectable(self) -> None:
        captured: dict[str, object] = {}

        def sender(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["auth"] = request.headers.get("Authorization")
            return json.dumps({"choices": [{"message": {"content": json.dumps(plan_payload())}}]}).encode()

        model = OpenAICompatibleModel(
            base_url="https://api.example.test/v1",
            api_key="test-key",
            model="gpt-test",
            request_sender=sender,
        )
        response = model.complete(system_prompt="system", user_prompt="user")

        self.assertEqual("https://api.example.test/v1/chat/completions", captured["url"])
        self.assertEqual("Bearer test-key", captured["auth"])
        self.assertEqual("gpt-test", captured["body"]["model"])
        self.assertEqual(json.dumps(plan_payload()), response)
        self.assertEqual("https", urlparse(str(captured["url"])).scheme)

    def test_contract_schemas_are_valid(self) -> None:
        for name in ("task-controller-plan.schema.json", "task-controller-report.schema.json"):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    unittest.main()
