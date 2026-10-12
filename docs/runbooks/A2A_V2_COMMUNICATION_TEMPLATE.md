# A2A v2 — simple human-readable communication contract

**Routing:** [TaskController Mailbox v2 Runbook](TASKCONTROLLER_MAILBOX_V2.md) is the canonical entrypoint. This file is only its format reference; it does not define a second authority gate.


**Goal:** GPT and Hermes keep moving. Every meaningful turn is **one** lightweight COMMAND, REPORT, CORRECTION or ACK and advances a single per-run **communication sequence**. Do not route source recovery, code sync, questions, ordinary regression findings or routine delegated execution instructions through lease/issuer scripts just to communicate.

## Exact communication template

```md
<!-- dw.taskcontroller.communication/v2 -->
### A2A v2 · COMMAND #1
run: scrum781-q0-fresh-20261010-r1
seq: 1
from: GPT
to: Hermes
kind: COMMAND
source_ref: github://nhatnguyenquang1838-coder/gwc/issues/595
reply_to: none

**GOAL**
Recover original Q0 source baseline, parent RuntimePlan and DWO incident fixture.

**NEXT**
Execute native P1 source recovery in admitted scope. Return exact refs/digests,
test evidence, remote/local HEAD, writer and the next legal action.

**EVIDENCE**
Existing continuation #6098492473 C3/E2, Q0 remote @80a3995...
```

Hermes replies with the same shape using `REPORT #2`, `from: Hermes`, `to: GPT`, `reply_to: <real prior comment URL>`; GPT's next `COMMAND #3`. Human-readable text is authoritative only for **communication intent**, not for execution rights.

## Minimal operational rules

1. **One turn, one command, seq+1.** Before posting, read only comments bearing the communication marker for this run, check the last sequence, and use the next number. Serialized single-writer append and exact comment-ID readback are required. A lost response should re-read before retry; never blind-post duplicate sequence.
2. **Read, consume, ACK.** Receiver reads the specific comment URL, validates run/seq/recipient, and replies with a higher-sequence REPORT/ACK. Its consumed cursor advances only after actual consumption, not notification or observation.
3. **Never block on ordinary drift.** Every NEXT should execute safe work immediately. GPT/Hermes exchange exact Git HEAD, local/remote sync, changed paths, tests and owner. Any effect must still comply with the actual governing project/GWC gate and human-tokenized approval when applicable; the mailbox adds no extra gate.
4. **Authority is external to communication.** The envelope transports intentions and evidence, not approval tokens. Merge, deployment, production, migration, data or secret actions follow the owning project's authority and, when GWC applies, its human-tokenized G0–G6 gates. Existing in-flight machine bindings cannot be silently bypassed or relabeled: historical #595 C3/E2 and expired attempt3 remain unchanged until the active runtime explicitly migrates them. Keep communication seq distinct from legacy C/E event seq.
5. **Existing #595 comments are history.** Adoption begins at a **separately recorded communication stream start** under #595 with seq 1; do not call historical Markdown comments typed records retroactively. No separate issue is necessary.
6. **Crash/concurrency:** GitHub issue comments lack cross-process atomic compare-and-swap. Single writer is mandatory; if concurrent writes race or seq forks, stop that one append, re-read and reconcile. This does not block independently authorized engineering.

## Implementation status

`taskcontroller/interaction/communication_v2.py` is one small standalone render/parse/seq helper. It has **no GitHub write, remote authentication, delivery, ACK persistence or Hermes Desktop host integration yet**. For live use, qualify a thin host connector that (i) appends under single-writer ownership, (ii) exact-reads comment ID and seq, and (iii) passes pointer to the actual Executor session. Do not pretend that posting normal prose or running the codec completes delivery.

This keeps v2 communication simple. Effect authorization remains the responsibility of the governing project/GWC lifecycle rather than a newly invented mailbox-level gate.
