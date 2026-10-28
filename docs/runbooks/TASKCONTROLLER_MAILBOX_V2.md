# TaskController Mailbox v2 — Communication-First Runbook

**Canonical entrypoint for GPT ↔ Hermes A2A communication.** The human-readable [communication template](A2A_V2_COMMUNICATION_TEMPLATE.md) is subordinate to this runbook. When TaskController mode is explicitly activated, use this runbook to communicate. Do not load a standalone v1 mailbox, issue a duplicate mailbox, or request a lease just to exchange information.

## Ultimate operating goal

Keep both peers reasoning, communicating, syncing code and fixing issues without deadlock. Every **meaningful** exchanged message is one durable human-readable v2 communication envelope, with monotonically increasing per-run communication `seq`. A `COMMAND` is a request/instruction in an existing authority scope, never an authority grant. Hermes may question, report blockers and independently pursue authorized solutions.

## Discover the recipient — A2A Agent Card concept

Before routing an exchange, resolve the recipient's current **Agent Card** (or a locally registered agent descriptor mapping the equivalent fields) rather than assuming a bot title or stale session. Agent Card provides discovery, not approval.

| Agent Card concept | Required decision |
| --- | --- |
| `name`, `description`, `version` | Who is the recipient and what agent build is advertised? |
| `skills` | Does it claim source-recovery, test/fix, local code sync, or TaskController capability? |
| `supportedInterfaces` | Which **verified, reachable** message endpoint/adapter is bound? |
| `capabilities` | Can it receive/stream messages or continue tasks? |
| `defaultInputModes`, `defaultOutputModes` | Can it consume `text/plain`? |
| `securitySchemes` / `securityRequirements` | How is the actual sender/recipient authenticated? |

An advertised capability is not a live session receipt. Resolve real `session_id`, `agent_instance` and receiver availability separately. If no working delivery route is admitted, keep independent authorized engineering moving and give an actionable transport-owner blocker.

Reference: [A2A Agent Card](https://a2a-protocol.org/latest/specification/) and [Agent Cards and skills](https://a2a-protocol.org/latest/tutorials/python/3-agent-skills-and-card). Agent Card fields and `Message / Task / Artifact` concepts are design inputs; this lightweight GitHub comment codec is **not** a claim of standards-level A2A wire compatibility.

## One communication envelope

Use [A2A v2 Communication Template](A2A_V2_COMMUNICATION_TEMPLATE.md). The minimal human-readable sections are **GOAL**, **NEXT**, and **EVIDENCE**, with header `run/seq/from/to/kind/source_ref/reply_to`.

1. Read this run's latest sequence and authenticated sender; write **one** communication message (`COMMAND`, `REPORT`, `CORRECTION`, `ACK`) using the template. Every meaningful exchange advances one **shared communication seq**, irrespective of actor. Do not consume/reset C/E protected mailbox seq or continuation to communicate.
2. Persist through one serialized GitHub comment writer, exact-read the new comment URL and content, then notify the verified recipient. An unread or unacknowledged comment is **posted**, not delivered/consumed. When retrying after unknown result, readback first to avoid duplicate seq.
3. Recipient consumes the source-bound message, checks task, sender, `seq`, `source_ref`, scope, and relevant current code HEAD; produces the next `REPORT/ACK` or independently fixes within existing delegated scope. Cursor advances on actual consumption, not passive observation.
4. **Do not conflate observer polling with a work cycle:** an unchanged raw cursor is a silent no-op (zero LLM turns and zero escalation). For a **qualified work cycle** needing GPT, distinguish verified `GPT_BUSY` (fail-fast duplicate GPT invocation, retain one correlated pending request) from verified `GPT_IDLE` (continue any legal local NEXT, otherwise after one bounded no-progress cycle escalate **once** with exact evidence and owner). If GPT state is not verified, do not infer busy/idle; diagnose the transport in a bounded way. The decision table and deduped stall key are in `docs/runbooks/HERMES_DESKTOP_RUNTIME.md#GPT-liveness--bounded-no-progress-decision-gpt_busy-vs-gpt_idle`.

## Loop liveness is not mailbox delivery admission

Use the [Hermes Desktop liveness decision table](HERMES_DESKTOP_RUNTIME.md#GPT-liveness--bounded-no-progress-decision-gpt_busy-vs-gpt_idle) for host state, stalled-work-cycle counting and exactly-once escalation. **Delivery:** a newly posted `COMMAND` has a comment URL/seq but is not `consumed` until the actual recipient reads and acknowledges it. The absence of a `REPORT` does not prove GPT/Hermes is busy, idle, or that a new command should be duplicated. The A2A v2 conversation seq counts messages, not timer observations and not the old machine C/E logical seq.

`ROUTE_BINDING_MISMATCH` for an obsolete scheduler row is not a general prohibition on the current GWC Q0 source recovery, code synchronization and test/fix work. Keep that old Loop isolated; resolve a new host route through genuine current-session evidence when needed. Do not silently rebind, resume or invent an active Loop from a communication comment. Existing GWC gate and Human-tokenized authority remain independent of mailbox communication.

## Mailbox is NOT an additional effect gate

**Retire the label `PROTECTED_EFFECT` from communication classification.** There is one simple mailbox communication lane. Classify a message as `COMMAND/REPORT/CORRECTION/ACK` by conversational intent, not by whether it contains verbs like `fix`, `push`, `merge` or `deploy`.

**Effect authority belongs to the owning system, never to the envelope.** If GWC governs a run, applicable G0→G6 gates and human-tokenized approval own merge, deployment and production decisions. Otherwise current repository/project authority owns them. A comment does not mint permission or substitute a required gate. A messenger may carry an authorized execution instruction but cannot override actual target enforcement. Do not introduce a second mailbox-level approval/lease sequence for ordinary command exchange.

**Compatibility boundary:** Existing `dw.taskcontroller.mailbox/v2` typed execution events, issuer WorkLeases and #595 C/E continuation have not been migrated by this communication change. Do not impersonate those records, reuse an expired attempt, or relabel a new comment as an old C4 event. Any existing specific runtime with a bound effect admission contract must still satisfy that existing contract until an approved runtime migration replaces it. This is legacy execution-path compatibility, **not** a new `PROTECTED_EFFECT` classification that blocks dialogue.

## Code-sync and self-remediation

Every material handoff includes `repo, branch, remote HEAD, Hermes Local HEAD, changed paths, tests, writer, NEXT`. Hermes Local fetches/compares remote, merges published evidence-bearing branches additively (rebase only disposable unpublished local changes), reruns tests, and pushes its changes before claiming GPT can consume them. GPT exact-reads the published commit. Neither peer waits for per-step permission for in-scope RED→FIX→GREEN→replay.

## Minimal acceptance criteria

- **AC1:** GPT COMMAND #1 → Hermes REPORT #2 → GPT COMMAND #3, each durable readback and actual receiver ACK; no authority-script roundtrip to post a message.
- **AC2:** Existing #595 native Q0 P1 source-recovery NEXT moves even while old C3/attempt3 remains expired; no fabricated C4.
- **AC3:** Agent Card skills/interface resolved, authenticated delivery and exact local session recipient; no guessed session from a title.
- **AC4:** A routine source update creates no extra mailbox approval; code remote/local synchronization verified.
- **AC5:** Missing receiver/transport creates a targeted blocker; both peers continue independent work and escalate shared stagnation with options.
- **AC6:** No weakening of GWC gates, separately tokenized human approvals, protected-main, production or scope rules.

**Implementation status:** `taskcontroller/interaction/communication_v2.py` currently implements render/parse/sequence logic, not authenticated GitHub remote append, delivery/consumed ACK, Agent Card registry or Hermes live binding. Qualification is required before claiming a working automatic communication channel.
