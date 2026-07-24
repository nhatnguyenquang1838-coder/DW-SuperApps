# Impact Analysis

## Direct impact

- Adds distribution files and publishing automation to Task Me.
- Makes `.kiro/skills/implementation-task-architect/SKILL.md` portable across supported hosts.
- Separates distributable skill source from Task Me's own generated `.ua` planning outputs.

## Risks

- Packaging `.task-architect/config.json` with repository-specific source paths could misconfigure consumers.
- Including `.ua/generated/**` would violate the no-plan/no-task package rule.
- Missing a reference file would make the skill unusable after extraction.
- Installation could accidentally invoke the planning skill.

## Controls

- Ship schema/default templates rather than repository-specific active configuration where appropriate.
- Assert no generated output folder is present.
- Validate every file reference from the skill and reference documents.
- Smoke test installation without invoking task generation.
