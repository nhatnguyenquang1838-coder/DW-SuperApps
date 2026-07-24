# BMAD Method Knowledge Model

Generated with the Understand Anything graph contract from:

- Repository: `nhatnguyenquang1838-coder/BMAD-METHOD`
- Source commit: `bb45db4aa4496c69239f9c0629c290fd1b072fc9`
- Package version observed: `6.10.0`

## Architectural conclusion

BMAD is split into four runtime-relevant areas:

1. Core orchestration and shared configuration.
2. BMM lifecycle skills from analysis through implementation.
3. Universal installer and renderer required to materialize host-specific skills.
4. Shared scripts used by installed skills.

The DW distribution includes those runtime areas and excludes the documentation website, generated web bundles, evals, tests, and development-only artifacts.

## Files

- `knowledge-graph.json` — UA-compatible structural graph.
- `architecture.mmd` — compact semantic-color Mermaid view.

No Understand Anything dashboard is bundled or required.
