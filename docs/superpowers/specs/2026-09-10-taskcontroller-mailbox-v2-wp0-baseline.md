# TaskController Mailbox Revamp v2 — WP0 Baseline

**Status:** WP0 evidence complete; v2 production implementation not yet started.

## Binding

| Field | Evidence |
|---|---|
| Architecture source | Notion page `04 — TaskController Mailbox Revamp · C4 Architecture` |
| Source URL | `https://app.notion.com/p/04-TaskController-Mailbox-Revamp-C4-Architecture-3d607c1c65b6818c9482ca9848e06d62` |
| Detailed task source | API-derived snapshot `/Users/mac/.hermes/cache/notion-api/detailed-implementation-tasks.md` |
| Detailed snapshot SHA-256 | `290e041d30a0bd8181709b7c847102cb5dcac6defdca3a038cd203e26327116c` |
| Base commit | `eb6d611b2fe16c3fd2b0453695667a6b5fb2d3da` (`origin/main` at branch creation) |
| Implementation branch | `feat/taskcontroller-mailbox-v2-base` |
| Isolated worktree | `/Users/mac/prj/DW-SuperApps.worktrees/auto/taskcontroller-v2-base` |
| Current protocol evidence | `dw.taskcontroller.a2a/v1` |

The shared checkout's pre-existing dirty paths were not copied into or modified by this worktree. No merge, deploy, external mailbox write, Slack post, Jira mutation, or Notion mutation was performed.

## Current v1 component map

| Concern | Current concrete implementation | Regression evidence |
|---|---|---|
| Envelope identity and protocol | `taskcontroller/interaction/envelope.py`: `A2AEnvelope` (line 40), `EnvelopeKind` (line 24), required text validation (line 33) | `tests/taskcontroller/test_reference_a2a.py::test_envelope_round_trip_is_deterministic_and_reference_based`; `::test_envelope_invalid_core_fields_fail_closed` |
| Actor sequence/cursor | `taskcontroller/interaction/envelope.py`: `MailboxCursor` (line 166); cursor accepts strictly newer sequence per actor | `tests/taskcontroller/test_reference_a2a.py::test_cursor_accepts_only_strictly_newer_sequence_for_same_actor`; `::test_cursor_round_trip_supports_recovery_without_chat_history` |
| GitHub mailbox representation | `taskcontroller/interaction/github_mailbox.py`: `render_mailbox_comment` (line 19), `parse_mailbox_comment` (line 40), `mailbox_operation` (line 68); current v1 is mutable one-comment/one-actor-marker binding | `tests/taskcontroller/test_reference_a2a.py::test_github_mailbox_comment_round_trip_has_one_actor_marker`; `::test_mailbox_parser_rejects_sender_marker_mismatch_and_multiple_markers`; `::test_mailbox_operation_preserves_one_actor_one_comment_semantics` |
| Durable continuation | `taskcontroller/interaction/continuation.py`: `MailboxPollTarget` (line 50), `ControllerContinuation` (line 73), `ContinuationStore` (line 231), `persist_before_dispatch` (line 251), `recover_continuation` (line 242) | `tests/taskcontroller/test_controller_continuation.py::test_continuation_checkpoint_round_trips_through_existing_run_ledger`; `::test_checkpoint_rejects_non_durable_or_non_monotonic_wait_state`; `tests/taskcontroller/test_a2a_runtime_session.py::test_recovery_uses_persisted_continuation_and_controller_mailbox_not_slack_history` |
| Pointer-only wakeup | `taskcontroller/interaction/wakeup.py`: `WakeupSignal` (line 21); `taskcontroller/interaction/human_projection.py`: `HumanEvent` and `project_envelope_for_human` (lines 25 and 69) | `tests/taskcontroller/test_wakeup_signal.py::test_wakeup_signal_round_trip_is_pointer_only`; `::test_wakeup_signal_invalid_fields_fail_closed`; `tests/taskcontroller/test_reference_a2a.py::test_human_projection_compacts_machine_events` |
| Hermes/runtime bootstrap and poll | `taskcontroller/runtime/session.py`: `TaskControllerRuntimeSession` (line 60), `boot_taskcontroller_session` (line 246), `dispatch_taskcontroller_command` (line 303), `poll_executor_mailbox` (line 370), `recover_taskcontroller_session` (line 436) | `tests/taskcontroller/test_a2a_runtime_session.py::test_boot_materializes_both_mailboxes_persists_checkpoint_and_exact_readbacks`; `::test_poll_reads_only_bound_executor_mailbox_and_accepts_exact_expected_seq`; `::test_poll_ignores_stale_equal_seq_but_fails_closed_on_sequence_gap`; `::test_boot_fails_closed_when_controller_mailbox_exact_readback_differs` |
| Legacy Slack pilot adapter | `taskcontroller/mvp/pilot.py`: `SlackTransport` (line 439), `HermesExecutorClient` (line 476), `SlackWebApiTransport` (line 807), `MvpPilot` (line 1009); actor filtering and human-readable report parser remain v1 compatibility behavior | `tests/taskcontroller/test_mvp_pilot.py::test_controller_posts_command_executor_replies_later`; `::test_read_returns_only_executor_authored_reports`; `::test_loop_reads_only_executor_reply_not_controller_command`; `::test_dispatch_command_without_executor_id_fails_closed`; `::test_registry_and_package_mark_legacy_slack_pilot_compatibility_only` |
| Runtime CAS/store | `taskcontroller/runtime/store.py`: `StateStore` (line 33), `RuntimeRecord` (line 64), `InMemoryStateStore` (line 77), snapshot/replay sidecars | `tests/taskcontroller/test_checkpoint_recovery_c3.py::test_checkpoint_captures_state_version_and_all_sidecars`; `::test_event_journal_payload_is_replay_sufficient`; `::test_two_consecutive_recoveries_yield_same_state_and_sidecars` |
| Event dedupe/sequence/fencing | `taskcontroller/runtime/event_router.py`: canonical fingerprint (line 38), `EventRouter` (line 93); current event route correlates run/node/execution/attempt and checks active lease/fence | `tests/taskcontroller/test_event_router_c1.py`; `tests/taskcontroller/test_checkpoint_recovery_c3.py::test_recovery_preserves_dedupe_watermark_fencing_current_lease` |
| Lease lifecycle | `taskcontroller/runtime/lease.py`: `LeaseManager` (line 173), explicit grant/current/release/revoke/expire/renew paths | `tests/taskcontroller/test_lease_c2.py`; `tests/taskcontroller/test_checkpoint_recovery_c3.py::test_lease_grant_appends_two_records_detach_then_grant` |

### Current boundary observed

The current runtime already has CAS, journal, dedupe, event correlation, lease/fence, continuation and pointer wakeup primitives. They are not yet a normative `dw.taskcontroller.mailbox/v2` append-only event contract: v1 GitHub mailbox comments remain mutable, and the eight-contract §23.11 foundation gate has not passed. WP5/WP6 runtime fan-out and cross-review therefore remain disabled.

## v1 compatibility fixtures

Fixture path: `tests/taskcontroller/fixtures/v1_contract_fixtures.json`

The fixture was generated from the current v1 `A2AEnvelope.to_dict()` and `render_mailbox_comment()` implementations on the base commit, not hand-authored from the architecture prose. The regression consumer is `tests/taskcontroller/test_v1_contract_fixtures.py`.

Captured cases:

- `valid_request`: command envelope and rendered mailbox body round-trip.
- `executor_progress`: report/progress envelope round-trip.
- `terminal_result`: terminal envelope round-trip.
- `duplicate_delivery`: identical payload/body is byte-equivalent on retry.
- `stale_sequence`: cursor rejects a sequence that is not strictly newer.
- `invalid_requests`: missing required identity, unsupported protocol, and unsupported kind fail closed.

Focused result: `5 passed in 0.02s`.

## Baseline E2E/regression fence

All commands were executed from the isolated worktree with:

```text
/Users/mac/.hermes/hermes-agent/venv/bin/python -m pytest ...
```

| Scope | Result |
|---|---:|
| v1 fixture regression | `5 passed in 0.02s` |
| Existing mailbox dispatch/resume, pilot, checkpoint/recovery, runtime-session scenarios (`test_reference_a2a.py`, `test_mvp_pilot.py`, `test_checkpoint_recovery_c3.py`, `test_a2a_runtime_session.py`) | `98 passed in 0.22s` |
| Full `tests/taskcontroller` suite after fixture test addition | `1026 passed in 1.03s` |

The full suite is the current regression fence for subsequent v2 changes. Any later failure must be classified as an intended additive v2 change or a regression; it must not be hidden by weakening v1 tests.

## Explicit v1/v2 compatibility boundary

Statuses use the architecture/task contract vocabulary: `SUPPORTED`, `LOSSLESS_ADAPTER`, `REPLAN_REQUIRED`, and `DOWNGRADE_UNSUPPORTED`.

| Producer → consumer / behavior | Status | Boundary decision |
|---|---|---|
| v1 Controller ↔ v1 Executor, mutable GitHub mailbox comments, actor markers and current cursor semantics | `SUPPORTED` | Preserve unchanged for existing v1 sessions during rollout. Fixture and existing suite are compatibility inputs. |
| v1 continuation-before-dispatch and pointer-only v1 `WakeupSignal` | `SUPPORTED` | Preserve the recovery invariant; v2 may add checkpoint/intent binding but may not require chat replay. |
| Existing v1 Slack RootCard/human projection | `SUPPORTED` | Slack remains projection/wakeup only; it is never canonical execution state. |
| Current v1 runtime CAS, journal, dedupe, event-router correlation and lease/fence primitives | `SUPPORTED` | Keep the primitives stable while v2 adapters bind stronger identity and append-only acceptance. |
| v1 producer → v2 consumer when the v1 payload contains all required common fields and no v2-only semantics are requested | `LOSSLESS_ADAPTER` | Parse through an explicit v1 compatibility adapter; never infer absent generation, boundary, manifest or Mixer-seal semantics. |
| v2 producer → v1 consumer for an atomic request whose required fields can be losslessly represented | `LOSSLESS_ADAPTER` | Use an explicit adapter and retain the v1 semantics; do not silently emit a semantically weaker v1 message for a v2-only request. |
| v2 append-only events, immutable event identity, producer namespace, plan/contract/boundary/source/standards digests, attempt and lease-generation identity | `SUPPORTED` (v2↔v2 only) | Implement as additive v2 behavior; no v1 mutable-comment rewrite may claim to represent these fields. |
| v1 producer → v2 consumer requiring current generation, execution boundary, Fanout Manifest, join/reuse, or Mixer seal | `REPLAN_REQUIRED` | Replan/upgrade the request with explicit v2 fields; missing semantics are not inferred. |
| v2 request/result requiring fan-out, cross-review, child lifecycle, manifest/join/reuse, or Mixer seal sent to a v1 Executor | `DOWNGRADE_UNSUPPORTED` | Reject downgrade or route to a v2-capable AgentInstance; no silent semantic loss. |
| Slack text modified/deleted while the canonical mailbox is intact | `SUPPORTED` | Hermes/Controller reconstruct from exact mailbox evidence; Slack text is not task authority. |
| Direct-message/chat-history replay as a v2 recovery source | `DOWNGRADE_UNSUPPORTED` | v2 recovery must use continuation + canonical mailbox/event evidence; conversation history is not canonical state. |

### Non-goals frozen by WP0

- No runtime fan-out/cross-review activation before all eight §23.11 machine-complete foundation contracts and negative tests pass.
- No replacement of v1 mutable mailbox semantics in the v1 lane.
- No generic kernel branching on a Hermes provider name; provider-specific behavior remains in adapters.
- No merge to `main`, deploy, or external-system mutation from this branch without a later explicit governed checkpoint.

## WP0 exit decision

`WP0 = PASS` for baseline/inventory/regression-fence scope. This is **not** the eight-contract foundation approval and does not authorize WP5/WP6 runtime fan-out. The next production implementation boundary is WP1/P1 normative v2 contract work; DWA will run Pattern E fanout at that human-approval checkpoint and continue only if the synthesized verdict is `PASS`.
