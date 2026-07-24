# Coding Guide

## Recipe design

Prefer explicit paths and narrow globs. For every included directory, document why the entire directory is required. Place deny patterns for `.gwc/tasks/**`, evidence directories, approval envelopes, generated reports, `docs/plans/**`, caches, `.env*`, and secrets.

## Dependency verification

Parse Markdown links, inline file references, schema `$ref` values, template references, and Python imports used by packaged validators. Tests must fail on a dangling internal reference.

## Consumer authority

The default consumer contract may authorize reads and writes only under the declared project runtime root and approved host adapters. Installation must not imply approval, merge, GitHub, Jira, Slack, or deployment authority.

## Workflow

Call the shared reusable workflow using an immutable DW-SuperApps commit. Keep provider workflow logic thin: checkout, pass recipe/power identity/channel inputs, and inherit only required secrets.
