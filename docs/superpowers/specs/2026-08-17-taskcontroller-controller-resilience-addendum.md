# TaskController Controller Resilience Addendum

Status: accepted enhancement for the reference-based A2A pilot.

## Problem

A ChatGPT Controller turn can end after dispatch or during a wait/poll cycle even when the TaskController run is not terminal. Therefore run liveness cannot be equated with the lifetime of one GPT response.

## Decision

Keep GPT as the decision-making Controller, but make continuation state durable and bounded.

Before any Executor wake/dispatch, the Controller MUST persist a continuation checkpoint and bind the same compact checkpoint into its durable mailbox envelope. The checkpoint contains only run/epoch/phase/next-action, exact mailbox pointers/cursors, exact head SHA, wake-up binding, and Human RootCard ref.

An ACTIVE checkpoint forbids a semantic final/terminal Controller response. A fresh Controller execution recovers from the latest Controller mailbox checkpoint plus Executor mailbox cursor and exact referenced evidence; chat and Slack history are not recovery inputs.

## Polling

Polling reads only the exact Executor mailbox comment referenced by the checkpoint. It does not re-read the whole issue, Slack thread, or conversation. In-session cadence remains 60 seconds. Non-terminal waits remain in the same execution when the host stays alive.

## Hermes Cloud

For the current Hermes Cloud capability, `slack-websocket` wake-up is REQUIRED. Slack carries a pointer-only wake-up; the command/context remains in GitHub mailbox refs.

## Context bounds

A2A envelopes are bounded to keep recovery and polling cheap: request <= 4096 chars, state <= 8192 UTF-8 bytes, <=16 input refs, <=16 artifact refs. Large context/code remains behind exact durable references.

## Non-goal

This does not claim that ChatGPT UI can resurrect a fully terminated host execution by itself. It guarantees crash-safe run state and deterministic recovery when a new Controller execution starts.
