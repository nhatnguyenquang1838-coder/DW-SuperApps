# Controller Transfer — Login Epic Runtime Graph Reference

This folder is a controller-to-Hermes transfer package for SCRUM-555 / #80 / seq=5.

The raw sandbox artifacts are large, so the transfer is source-based and deterministic:

- `login_epic_reference_generator.py` regenerates:
  - `projects/dw-observation/fixtures/login_epic_10_runs_gwc_taskcontroller_data.json`
  - `login_epic_10_runs_gwc_runtime_graph.reference.html`
- `login_epic_ui_source_architecture.md` defines the clean source-code architecture Hermes should implement in repo source.

Required generated counts:

```text
run_count = 10
total_runtime_nodes = 243
every run contains: G0_CONTEXT, G1_ALIGNMENT, G2_EXECUTION, G3_PR, G4_MERGE, G5_DEPLOY, G6_PRODUCTION
```

Hermes instruction:

1. Use the generator as the reference dataset/HTML source, not as production UI source.
2. Implement production source using the architecture document.
3. When implementation is done, capture and reply in Slack with screenshots:
   - Epic overview showing 10 run cards.
   - Selected run showing G0→G6 gate clusters and arrows.
   - LIVE SIM/player active node and animated edge.
   - Right panel with Files/Artifacts modal opened.
4. Reply with head SHA, files changed, fixture counts, validation output, localhost URL, screenshot links/artifacts, DOM proof, and confirmation PR is not merged.

Exclusions preserved:

- no Supabase migration/apply
- no deploy/G6 action
- no pre-prod→main
- no unrelated lanes
- no GWC repo mutation
