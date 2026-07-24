# DW SuperApps Agent Routing

This repository is an orchestration workspace for multiple AI hosts, reusable Powers, model providers, and product systems.

## Discovery

1. Read `workspace.yaml`.
2. Resolve the target system under `systems/`.
3. Load only the Powers enabled for that system.
4. Treat each Power repository as independently versioned source.
5. Keep generated and runtime data inside the owning system repository.

## Power roles

- `powers/gwc`: governance and delivery workflows.
- `powers/ua`: semantic/codebase knowledge generation and query.
- `powers/task-me`: impact analysis and implementation task planning.
- `bmad` distribution: structured analysis-to-implementation delivery workflows packaged from pinned external BMAD source.

## Host neutrality

Supported hosts include Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and generic/custom agents. Host-specific folders expose only thin discovery adapters. They must not duplicate Power logic, schemas, or runtime data.

`bionics`, `biotic`, and `ollama` are accepted aliases for the generic `custom` host. Ollama itself is a model provider, not a host; its OpenAI-compatible endpoint is registered separately.

## Model providers

Local Ollama compatibility uses:

- Base URL: `http://localhost:11434/v1`
- API key placeholder: `ollama`
- Model: `OLLAMA_MODEL`, default `qwen3-coder:30b`

## Source-of-truth boundaries

- `DW-SuperApps` owns workspace registration, Power and system manifests, host-adapter generation, and orchestration commands.
- Each Power repository owns its instructions, schemas, tools, and release lifecycle.
- Each product repository owns application code and generated operational data.
- Generated host adapters are installation artifacts; canonical logic remains in the owning Power.
- Provider outputs, including `.gwc`, `.ua`, `.task-me`, and `.bmad`, remain system-owned runtime data.

## Safety

- Never write directly to protected `main`.
- Never overwrite unmanaged host files.
- Refuse dirty submodule updates.
- Never infer gate authority from Slack, Jira, or a generated adapter.
- Never commit secrets, credentials, populated runtime roots, caches, or generated dashboards.
- Preserve exact source SHAs and validation evidence for governed changes.
