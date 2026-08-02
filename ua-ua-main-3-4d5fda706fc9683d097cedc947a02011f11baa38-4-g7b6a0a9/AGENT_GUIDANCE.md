# DW Power Agent Activation Contract

This is static distribution guidance generated when the package was built. It is not a task prompt, not a shell command, and not authority to perform external writes.

## Package identity

- Power: `ua`
- Package version: `ua-main-3-4d5fda706fc9683d097cedc947a02011f11baa38-4-g7b6a0a9`
- Source: `nhatnguyenquang1838-coder/Understand-Anything@7b6a0a931a4f5c6f21eaf4a485738098b8f84286` (`HEAD`)
- Target-owned runtime root: `.ua/`

## Required activation behavior

1. Read the workspace `AGENTS.md` and `workspace.yaml`.
2. Resolve exactly one target system and read its local instructions.
3. Read this contract, `POWER.yaml`, `SOURCE.json`, and `MANIFEST.json`.
4. Select the applicable skill entrypoint from the declared list below.
5. Apply that skill directly to the user's request in the current conversation.

A native alias selects a skill; it is not something to execute in a terminal. Do not create a prompt-export command, ask the user to copy a generated prompt, or merely describe the Power instead of applying it.

When multiple entrypoints exist, load only the entrypoint whose scope matches the current task. A non-`SKILL.md` entrypoint is a supporting executable or module and must not be run unless the selected skill explicitly requires it and current authority permits execution.

## Declared package entrypoints

- `understand-anything-plugin/skills/understand/SKILL.md`
- `understand-anything-plugin/skills/understand-chat/SKILL.md`
- `understand-anything-plugin/skills/understand-explain/SKILL.md`
- `understand-anything-plugin/skills/understand-diff/SKILL.md`
- `understand-anything-plugin/skills/understand-dashboard/SKILL.md`
- `understand-anything-plugin/skills/understand-domain/SKILL.md`
- `understand-anything-plugin/skills/understand-onboard/SKILL.md`
- `understand-anything-plugin/skills/understand-knowledge/SKILL.md`
- `understand-anything-plugin/skills/understand-figma/SKILL.md`
- `scripts/power_help.py`

## UA task routing

Classify the request before acting:

- **Existing graph lookup:** requests to find, read, compare, show, or draw from the graph. Read the existing `.ua/knowledge-graph.json`; do not rebuild it, browse the web, or invent edges.
- **Graph refresh:** requests to update, regenerate, or rebuild the graph. Use the declared `/understand` entrypoint and write only under the selected project's `.ua/` runtime root.
- **Source analysis:** requests about code that are not graph lookups. Use the graph first when it exists, then read source files only where the selected skill requires it.

For an existing graph lookup:

1. Resolve the target project from `workspace.yaml`; do not silently assume a project when the request is ambiguous.
2. Confirm the graph file exists and note its `project.gitCommitHash`; warn when project-scoped changes may make graph context stale.
3. Search node `name`, `filePath`, `summary`, and `tags`; record exact matching node IDs and types.
4. Follow only edges whose `source` or `target` is a matched node. Check layer and tour membership separately.
5. Answer from that subgraph. Label file reads, inferences, and graph facts distinctly.
6. If drawing Mermaid or another diagram, render the extracted nodes and edges exactly; never add a visual edge merely because two documents seem related.

Useful user requests:

- `Find the installation-guide node in the current UA knowledge graph. No web search, no rebuild.`
- `Show the one-hop graph around document:docs/installation/INSTALL_POWERS.md.`
- `Refresh the UA knowledge graph for this project, then report what changed.`


## Ownership and safety

- Power package files remain in the DW-SuperApps workspace store.
- Runtime state and project configuration remain under the selected target's `.ua/`.
- Do not create a target-local `.dw/powers` installation.
- Installation, configuration, sanity, doctor, history, rollback, and uninstall are lifecycle operations; none of them grants merge, deployment, release, credential, migration, production-data, or approval authority.
