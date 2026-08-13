# TaskController in ChatGPT

`TaskController` is a generic controller engine. ChatGPT is supported through a
host bridge, so the local runtime does not pretend to call a ChatGPT UI or
conversation directly.

## ChatGPT host flow

```python
from scripts.dw_task_controller import (
    ChatGPTControllerBridge,
    TaskRequest,
)

bridge = ChatGPTControllerBridge()
request = TaskRequest(
    task_id="TASK-1",
    title="Controller pilot",
    objective="Compile a bounded implementation plan",
)

envelope = bridge.prepare_plan_request(request, {"repository": "DW-SuperApps"})
# Send envelope.to_payload()["systemPrompt"] and ["userPrompt"] to ChatGPT.
# Require one JSON object matching envelope.to_payload()["responseSchema"].
plan = bridge.compile_plan_response(request, chatgpt_response_text)
run = bridge.start_run(plan, run_id="run-1")
decision = bridge.process_report(run, executor_report)
```

The ChatGPT response must contain 3–5 subtasks. Every subtask declares its
allowed work, expected output, reporting requirement, and the required
`CONTINUE`, `WAIT_CONTROLLER`, or `TERMINAL` boundary.

## API-compatible GPT flow

For a GPT or Ollama endpoint that implements `/chat/completions`, use
`OpenAICompatibleModel` with `TaskController`. The adapter is transport
injectable for tests and reads credentials from the caller; this repository does
not contain provider secrets.

```text
python scripts/dw_task_controller.py plan \
  --task-id TASK-1 \
  --title "Controller pilot" \
  --objective "Compile a bounded implementation plan" \
  --base-url https://api.example.test/v1 \
  --model gpt-model
```

## Boundary

This MVP owns plan compilation, report validation, contracted subtask
transitions, and bounded intercept decisions. It does not own GWC authority,
Slack transport, worker spawning, Git mutation, merge, deployment, lease
fencing, replay, or multi-executor scheduling.
