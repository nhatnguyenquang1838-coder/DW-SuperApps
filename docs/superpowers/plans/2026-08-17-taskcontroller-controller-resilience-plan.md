# TaskController Controller Resilience Implementation Plan

1. RED: add continuation/recovery contract tests.
2. Implement `ControllerContinuation`, exact `MailboxPollTarget`, Run Ledger manifest persistence/readback, mailbox checkpoint binding, and ACTIVE final guard.
3. Bound A2A request/state/reference counts.
4. Promote continuation checkpoint from deferred to active MVP registry behavior.
5. Mark Hermes Cloud Slack WebSocket wake-up as required provider capability.
6. Update ChatGPT/A2A authority text so pre-dispatch order is persist -> mailbox write/readback -> wake -> poll.
7. Validate exact PR head with TaskController CI; classify global Power-compatibility failure separately.
8. Run a live multi-round recovery pilot before declaring Controller liveness fully proven.
