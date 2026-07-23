# Slack Notification Runbook

## Purpose

Publish GWC execution visibility updates to Slack when the capability is available.

Slack is a notification channel only. It is not the source of truth.

## Authority

- GWC state engine: governance truth
- GitHub: code and CI truth
- Jira: tracking projection
- Slack: collaboration visibility

## Gate transition behavior

For every gate transition:

1. Persist GWC state.
2. Create audit event.
3. Attempt Slack notification when available.
4. Continue execution if Slack is unavailable.

## Failure handling

Slack failure must not block delivery execution.
The failure should be recorded in audit metadata.

## Future extension

Slack interaction may later support human approval actions, but approval authority remains in GWC.
