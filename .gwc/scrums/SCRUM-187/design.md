# SCRUM-187: Fastlane Delivery Pipeline

| Field | Value |
|---|---|
| Key | SCRUM-187 |
| Parent | SCRUM-189 |
| Status | In Progress |
| Gate | G1 |
| Owner | GWC |
| Workers | gwc, task-me |

## Gate Control

GWC owns the gate. The FastLane workflow accelerates bounded delivery with governance guardrails.
GWC delegates the following gate-1 intents:
- `task-decomposition` and `validation-planning` to task-me

## Decision Frame

Gate G1 may pass only if the FastLane envelope satisfies:
- exact provenance binding to the repository and base SHA
- scope hash covers all scoped file reads and writes
- G2 approval command is exact and includes the scope hash prefix
- guarded branch is created from the locked base SHA
- only scoped files are modified within the approved file scope
- Draft PR is created with the exact head SHA
- no merge, deploy, release, production configuration, credentials, migration, or production data operations are authorized

## Evidence Bound to GWC

GWC consumes the following artifacts as gate evidence:
- `.gwc/tasks/SCRUM-187/g0/context-snapshot.yaml`
- `.gwc/tasks/SCRUM-187/g1/intake/g1-intake-brief.yaml`
- `.gwc/tasks/SCRUM-187/g1/preflight/g1-preflight-report.yaml`
- `.gwc/tasks/SCRUM-187/g1/brainstorming/g1-options.yaml`
- `.gwc/tasks/SCRUM-187/g1/decision/g1-decision-record.yaml`
- `.gwc/tasks/SCRUM-187/g2/fastlane-envelope.json`

## Authority Boundary

GWC remains the only actor authorized to transition gates G2, G4, G5, and G6.
The FastLane workflow is temporary and does not replace the GWC gate lifecycle.