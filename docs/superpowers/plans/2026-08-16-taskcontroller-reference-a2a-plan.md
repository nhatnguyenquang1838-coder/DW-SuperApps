# TaskController Reference-Based A2A Pilot — Implementation Plan

Date: 2026-08-16
Design: `docs/superpowers/specs/2026-08-16-taskcontroller-reference-a2a-design.md`
Base: `main@d021129ee296b1034584c52862d39dde83090197`
Branch: `feat/taskcontroller-reference-a2a-pilot`
Method: Superpowers `writing-plans` → `executing-plans`, TDD RED-GREEN-REFACTOR

## Execution boundaries

Active lane: **TaskController · Agent Interaction / Reference-based A2A**.

Excluded lanes:
- GWC / UA compatibility lock;
- SCRUM-288 / NA81;
- MSK, Kafka, NATS or webhook infrastructure;
- unrelated Slack UI work;
- production deploy/release.

Historical issue evidence:
- #48–#52 are closed but their implementation is only on unmerged PR #53 (`fa283f351d398f61fa849aef613aa78f2deaba65`) based on stale `main@992757f...`.
- Therefore they are **not dependency evidence on current main**. Ideas may be selectively ported only after readback.

## Task 1 — RED: interaction contract tests

Create `tests/taskcontroller/test_reference_a2a.py` first.

Test cases:
1. valid envelope round-trip is deterministic;
2. invalid empty identities / invalid sequence / unsupported kind fail closed;
3. existing `InputRef` is accepted and preserved as a reference rather than copied content;
4. cursor accepts strictly newer sequence from the same actor;
5. cursor rejects duplicate/stale sequence;
6. cursor state serializes/restores without conversation history;
7. GitHub mailbox comment has one deterministic actor marker and one latest envelope;
8. parsing rejects actor-marker/envelope sender mismatch;
9. rendering the same actor again produces a replacement body, not an append-only event stream;
10. raw protocol event maps to one bounded human semantic event or no human event.

Expected RED state: import/module failure because `taskcontroller.interaction` does not yet exist.

Verification:
- open Draft PR after RED commit;
- read TaskController validation for the exact RED SHA;
- failure must be attributable to the new tests, not an unrelated lane.

## Task 2 — GREEN: transport-neutral envelope and cursor

Create:
- `taskcontroller/interaction/__init__.py`
- `taskcontroller/interaction/envelope.py`

Implement:
- `A2A_PROTOCOL = "dw.taskcontroller.a2a/v1"`;
- `EnvelopeKind` enum: `COMMAND`, `REPORT`, `REVIEW_REQUEST`, `CORRECTION`, `TERMINAL`, `HEALTH`;
- immutable `A2AEnvelope` with `run_id`, `node_id`, `sender`, `recipient`, `seq`, `kind`, `inputs`, `artifact_refs`, `request`, `state`, `updated_at`;
- validation using existing `TaskControllerValidationError`;
- deterministic `to_dict` / `from_dict`;
- `MailboxCursor(actor, last_seen_seq, mailbox_ref?, last_head_sha?)`;
- `observe(envelope)` returns a new cursor only for the same actor and strictly newer sequence; stale/duplicate raises a specific interaction validation error or `TaskControllerValidationError` with stable semantics.

Do **not** modify WP0 `InputRef` schema.

Verification:
- focused new tests pass;
- full `tests/taskcontroller/` remains green on exact SHA.

## Task 3 — GREEN: deterministic GitHub mailbox codec

Create `taskcontroller/interaction/github_mailbox.py`.

Implement pure binding codec only; no GitHub SDK/network calls:
- actor marker: `<!-- taskcontroller:mailbox:<actor> -->`;
- deterministic JSON fenced payload containing latest envelope;
- concise forensic summary outside the JSON payload;
- `render_mailbox_comment(envelope)`;
- `parse_mailbox_comment(body)`;
- fail closed on malformed marker, multiple markers, protocol mismatch or sender mismatch;
- helper returning a host operation intent such as `CREATE_COMMENT` vs `UPDATE_COMMENT` based on whether a mailbox comment ID already exists.

This module is a GitHub binding representation, not domain authority.

Verification:
- codec tests pass;
- repeated render for same actor does not imply a second event/comment;
- no external SDK import.

## Task 4 — GREEN: human semantic compaction

Create `taskcontroller/interaction/human_projection.py`.

Implement:
- bounded `HumanEventKind`: `RUN_STARTED`, `SUBTASK_STARTED`, `MILESTONE_REACHED`, `REVIEW_REQUIRED`, `CORRECTION_REQUIRED`, `BLOCKED`, `AUTHORITY_REQUIRED`, `CONTROLLER_RECOVERED`, `TERMINAL`;
- immutable `HumanEvent` with concise title/status/detail/evidence refs;
- pure `project_envelope_for_human(envelope)`;
- normal low-level `HEALTH`/poll/no-op state changes may return `None`;
- `REVIEW_REQUEST`, `CORRECTION`, `TERMINAL` must produce human events;
- raw JSON/envelope body must never be copied into human detail.

This establishes the invariant `Machine State -> Human Projection` before any Slack transport.

Verification:
- projection tests pass;
- no Slack SDK import.

## Task 5 — Realign canonical TaskController instructions

Update these current-main authorities so they no longer define Slack thread as the Agent execution journal:
- `controllers/taskcontroller.yaml`
- `agents/README.md`
- `agents/chatgpt-agent/agent-instructions.md`
- `agents/shared/slack-controller-executor-protocol.md`
- `agents/chatgpt-agent/slack-controller-mvp.md`
- `agents/hermes/agent-instructions.md`

Required semantics:
- Slack = Human Control Plane / live RootCard + semantic timeline;
- GitHub reference mailbox = pilot Agent communication/evidence binding;
- GPT polls mailbox cursor/reference changes; it does not need to reread the full Slack thread;
- Slack polling may still be used for human PAUSE/STOP/APPROVE/MERGE input, not Executor progress transport;
- one actor = one mutable mailbox comment;
- context by exact reference;
- fresh Controller recovery from canonical state/mailbox/cursor, not chat history;
- future A2A HTTP/NATS/Kafka remain bindings, not core semantics;
- GWC remains opt-in.

Update `tests/taskcontroller/test_activation_contract.py` to lock these new authorities and reject regression to `Slack thread = structured execution journal`.

Verification:
- activation contract tests pass;
- full TaskController validation green.

## Task 6 — Notion architecture synchronization

Update the existing TaskController architecture/engineering pages, not a new parallel architecture:
- `01 — TaskController Architecture Specification · System Architect`;
- `02 — TaskController Implementation & Engineering Plan · Engineering Lead`;
- `03 — GPT Slack Controller Pilot & Agent Dispatch Playbook` if needed.

Add/replace sections describing:
- Human / Bootstrap-Recovery / Agent Coordination planes;
- GitHub Reference-Based A2A pilot;
- one-actor-one-mailbox;
- semantic Slack projection;
- recovery invariant;
- migration path to A2A HTTP/event bus.

Notion remains knowledge plane, not runtime mailbox.

## Task 7 — Live pilot bootstrap

After code/CI is green:
1. create or bind a GitHub issue/run mailbox for the pilot;
2. create one Controller mailbox comment;
3. use Slack only to bootstrap the human RootCard and, if needed, notify Hermes Cloud where its GitHub mailbox is;
4. require Hermes to create/update exactly one Executor mailbox comment and place engineering artifacts in a branch/Draft PR;
5. Controller polls the GitHub mailbox comment by sequence and resolves only referenced evidence;
6. Slack receives only semantic milestones and Controller health;
7. prove Controller can resume from mailbox + refs without rereading the execution Slack history.

If Hermes cannot write GitHub directly, classify it as a binding-capability gap and keep Slack as temporary dispatch bootstrap only; do not revert the architecture to Slack-as-journal.

## Task 8 — Review and delivery

- inspect complete PR diff;
- run exact-head TaskController CI;
- if CI is non-terminal, remain in-session, wait 60s and reread exact SHA;
- fix only authorized TaskController-lane failures;
- request code review / self-review for spec compliance and code quality;
- keep PR Draft until the live pilot or deterministic acceptance evidence is sufficient;
- do not merge without separate human authority.

## Definition of Done

- design + plan committed on a current-main branch;
- RED evidence captured for new tests;
- GREEN exact-head TaskController CI;
- current canonical TaskController instructions describe Slack as human plane and GitHub as pilot Agent binding;
- deterministic mailbox/cursor/recovery behavior exists;
- raw Agent protocol is compacted before Slack;
- Notion architecture is synchronized;
- live pilot evidence recorded or a precise external-capability blocker documented;
- PR remains reviewable and unmerged unless separately authorized.
