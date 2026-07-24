# Coding Guide

## Repository strategy

Prefer a thin wrapper repository when preserving a clear boundary between external upstream source and curated distribution logic. A fork is acceptable when upstream synchronization and attribution remain explicit. Do not rewrite or push to `Egonex-AI/Understand-Anything`.

## Source lock

Store the exact upstream repository, branch, SHA, observed timestamp, and package recipe version. Drift detection may open evidence or fail a scheduled run, but it must not silently update downstream consumers.

## Curation

Begin at `understand-anything-plugin/skills/understand/SKILL.md`. Resolve Markdown paths, agent references, JavaScript imports, package metadata, and runtime helper paths. Include license/notices required by upstream terms. Deny dashboard, web UI, VS Code extension, images, screenshots, historical specifications, and `.ua` outputs.

## Workflow safety

Validate the candidate package before updating `SOURCE.lock.json`. Keep release and distribution branch publication separate from downstream DW-SuperApps pinning.
