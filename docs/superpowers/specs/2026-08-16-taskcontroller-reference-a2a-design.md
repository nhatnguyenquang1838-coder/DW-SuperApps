# TaskController Reference-Based A2A Pilot — Design

Date: 2026-08-16
Status: Approved direction; implementation branch
Base: `main@d021129ee296b1034584c52862d39dde83090197`
Active lane: TaskController · Agent Interaction / A2A

## 1. Problem

TaskController currently assumes a Slack-mediated Controller↔Executor loop: Controller commands, Executor milestone reports, evidence and corrections accumulate in one Slack thread and GPT polls that thread incrementally.

That works for a small pilot but does not scale when agents run in different environments and the thread becomes both human UI and machine context. The resulting coupling causes:

- machine communication to compete with human readability;
- Controller recovery to depend too heavily on chat/thread history;
- repeated context transfer even when code/evidence already has durable references;
- weak portability to Hermes Cloud, Hermes Mac, Codex, local agents or future A2A servers;
- pressure to introduce Kafka/NATS/MSK before the actual agent interaction contract is proven.

The user-facing requirement is the opposite: a human should normally follow a run from **one Slack surface**, while machine coordination remains compact and mostly invisible.

## 2. Design principles

1. **Slack is the Human System of Engagement.** A human MUST be able to understand and control a normal run from Slack alone.
2. **TaskController state is the execution System of Record.** Conversation history and Slack are not canonical run state.
3. **GitHub is the first durable Agent coordination/evidence binding.** It is a pilot mailbox/reference substrate, not the domain model.
4. **GPT is bootstrap/recovery/control-plane reasoning.** A fresh Controller session must recover from references/cursors/checkpoints rather than replaying a long conversation.
5. **A2A is semantic, not transport-specific.** The same envelope semantics must later fit HTTP A2A, local IPC, NATS, Kafka/MSK or another binding.
6. **Reference over repetition.** Code, diffs, artifacts and context are addressed by exact refs; envelopes stay small.
7. **Machine events are compacted before Slack.** Slack receives semantic milestones, blockers, authority boundaries and terminal outcomes, not polling chatter.
8. **One actor, one mutable mailbox record.** Normal Agent status is updated in place instead of creating unbounded reply streams.
9. **Exact repository evidence.** Code references bind repository + exact SHA + path/range. Base drift is a typed exception, not an implicit assumption.
10. **No infrastructure-first expansion.** Do not add MSK/NATS/webhooks until the interaction semantics are proven with a binding GPT can already read.

## 3. Planes

```text
Human
  |
  v
Slack Human Control Plane
  - one RootCard per run
  - compact semantic timeline
  - PAUSE / STOP / APPROVE / MERGE when applicable
  - Controller health / last observation / recovery state

Controller GPT
  - decomposition / decisions / review / intercept
  - cursor-based mailbox reads
  - reference resolution only when needed

TaskController Interaction Contract
  - envelope
  - cursor
  - context/artifact references
  - semantic human projection

GitHub A2A Binding (pilot)
  - task/issue or PR conversation as durable mailbox surface
  - one mutable mailbox comment per actor
  - branch / Draft PR / exact SHA for engineering artifacts
  - inline PR comments for code-specific semantic review

Executor environments
  - Hermes Cloud / Hermes Mac / Codex / local agent
```

Notion remains the long-lived architecture/knowledge plane. It is not the runtime mailbox.

## 4. Pilot interaction topology

For one TaskController run:

- one Controller identity;
- one or more bounded Executors may exist eventually, but the first vertical slice supports one Executor;
- one GitHub task/issue or PR conversation is the mailbox container;
- one mutable Controller mailbox comment;
- one mutable Executor mailbox comment;
- branch/Draft PR contains engineering work;
- Slack has one RootCard and only meaningful human-visible updates.

The mailbox container is a binding detail. Canonical `run_id`, `node_id`, `execution_id` and attempt/fencing identities are never derived from GitHub comment IDs or thread IDs.

## 5. Envelope

The pilot introduces a runtime/binding-level `A2AEnvelope`. It is intentionally smaller than full run state.

Required semantics:

```yaml
protocol: dw.taskcontroller.a2a/v1
run_id: TC-...
node_id: ...
sender: controller|executor-id
recipient: controller|executor-id
seq: 17
kind: COMMAND|REPORT|REVIEW_REQUEST|CORRECTION|TERMINAL|HEALTH
state: optional bounded state
inputs:
  - input_id: execution-context
    source_ref: github://owner/repo@<sha>/path#Lx-Ly
    media_type: ...
artifact_refs: [...]
request: compact semantic request
updated_at: ...
```

Rules:

- `seq` is monotonic per sender mailbox.
- stale or duplicate `seq` is ignored/fails closed.
- the envelope carries references, not copied repository bodies.
- large payloads become artifacts/refs.
- the envelope is not approval authority.
- the envelope does not expose chain-of-thought.

For the first slice, existing `InputRef(source_ref, media_type)` should be reused rather than changing WP0 domain schemas solely for the pilot.

## 6. GitHub mailbox binding

### 6.1 Persistent mailbox comment

Each actor owns exactly one mutable comment with a machine marker, for example:

```text
<!-- taskcontroller:mailbox:hermes-cloud -->
```

The comment body contains the latest envelope and a short human-readable summary for forensic use. Normal progress updates replace that comment instead of appending a new comment.

### 6.2 Context and engineering references

Use exact refs such as:

- repository + exact base/head SHA;
- branch / Draft PR;
- file path + line/range;
- PR review thread ID for semantic code discussion;
- artifact digest/ref where available.

An Executor must verify the contracted base/head before mutating. Mismatch produces typed `BASE_DRIFT`/evidence-conflict behavior instead of silently proceeding.

### 6.3 Cursor

Controller keeps a small cursor per actor:

```json
{
  "actor": "hermes-cloud",
  "last_seen_seq": 17,
  "mailbox_comment_id": 12345,
  "last_head_sha": "..."
}
```

Polling reads mailbox metadata/body and resolves referenced artifacts only when `seq` advances or a required ref changes.

## 7. Slack Human Control Plane

Slack must be sufficient for normal human operation, but it must not mirror the raw mailbox.

### RootCard

Keep visible, when available:

- task/run objective;
- human owner/watcher;
- Controller identity and health;
- Executor identity/model/token/cost only when actually known;
- current bounded subtask and progress;
- branch / PR / exact HEAD / CI;
- risk/blocker;
- Now / Next;
- last material update;
- contextual PAUSE / STOP / APPROVE / MERGE.

Controller health adds:

- `ACTIVE | DISCONNECTED | RECOVERED | BLOCKED`;
- last observation time;
- checkpoint/cursor summary where useful to the human;
- recovery state without exposing raw protocol internals.

### Semantic timeline

Slack thread replies are emitted only for material human events such as:

- RUN_STARTED;
- SUBTASK_STARTED;
- MILESTONE_REACHED;
- REVIEW_REQUIRED;
- CORRECTION_REQUIRED;
- BLOCKED;
- AUTHORITY_REQUIRED;
- CONTROLLER_RECOVERED;
- TERMINAL.

Do not emit ACKs, polling heartbeats, file-read chatter, raw CI polling, mailbox seq changes or low-level retries.

## 8. Controller recovery

A fresh GPT Controller should recover with:

1. canonical run/task identity;
2. exact repository state;
3. latest Controller and Executor mailbox envelopes;
4. cursor / last-seen sequence;
5. active contract/subtask;
6. referenced PR/SHA/CI evidence;
7. latest Slack RootCard binding for continued human visibility.

Recovery MUST NOT require replaying the entire Slack thread or previous GPT conversation.

## 9. Transport abstraction

Core interaction APIs should look conceptually like:

```python
binding.read_mailbox(actor_ref, after_seq)
binding.publish_envelope(target_ref, envelope)
binding.resolve(source_ref)
```

The first binding is GitHub. Later bindings may implement A2A HTTP, local IPC, NATS or Kafka/MSK without changing Controller/Executor semantic contracts.

## 10. Options considered

### A. Slack as machine bus + shared file

Pros: immediately visible to GPT and human.
Cons: conflates machine/human planes; write ownership is awkward; thread/file history scales poorly.
Verdict: keep Slack as human projection/fallback, not default machine bus.

### B. Notion as shared runtime state

Pros: good collaborative docs and long-lived context.
Cons: poor fit for exact SHA/diff/code review and high-frequency coordination; requires new locking/cursor semantics.
Verdict: knowledge plane only.

### C. GitHub reference mailbox — selected

Pros: durable, already readable/writable by GPT connector, native exact SHA/branch/PR/diff semantics, mutable comments, review threads, CI evidence.
Cons: not a true event bus; Controller still polls; GitHub availability remains an external binding dependency.
Verdict: best pilot to prove Agent interaction before adding infrastructure.

## 11. Scope of first implementation slice

Implement only the transport-neutral interaction primitives and a deterministic GitHub mailbox representation:

- typed envelope + validation;
- monotonic cursor/dedupe behavior;
- reference-only inputs using existing `InputRef`;
- deterministic serialize/parse format for a persistent GitHub mailbox comment;
- semantic human-event projection primitives sufficient to keep raw machine events out of Slack;
- tests first.

Do not implement live GitHub HTTP credentials inside TaskController. The ChatGPT/GitHub connector or another host adapter performs external reads/writes.

## 12. Non-goals

- no Kafka/MSK/NATS deployment;
- no webhook daemon for ChatGPT;
- no multi-executor scheduler in this slice;
- no GWC changes;
- no merge/deploy authority changes;
- no Notion runtime database;
- no requirement to merge stale PR #53;
- no raw Slack-thread execution journal as the canonical Agent protocol.

## 13. Acceptance criteria

The slice is accepted when:

1. a mailbox envelope round-trips deterministically;
2. duplicate/stale sequence is rejected/ignored deterministically;
3. repository/code context is represented by refs rather than copied file bodies;
4. GitHub comment serialization preserves one-actor-one-mailbox semantics;
5. machine events can be compacted to a bounded set of human events;
6. no Slack SDK/GitHub SDK/Notion dependency leaks into domain semantics;
7. current TaskController tests plus new interaction tests pass on the exact PR head;
8. a fresh Controller can, at least in deterministic tests, reconstruct the latest mailbox state from the newest envelope + cursor without conversation history.
