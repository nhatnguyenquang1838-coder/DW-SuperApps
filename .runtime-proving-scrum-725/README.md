# RP-CERT-001 SCRAM-725 W7 Correction Baseline (seq26)

Append-only sanitized certification evidence for campaign RP-CERT-001 CORRECTED baseline.
This branch never merges, never deploys, never contains runtime/product code.
A fresh verifier reconstructs verdicts from manifest.json + events.jsonl
without original host /tmp, GPT/Hermes transcript, or Slack replay.

## Correction context
- Controller command: cmd-023-scrum-725-w7-evidence-binding-correction (seq26)
- Root cause: GitHubEvidenceBinding.commit_sha created circular self-binding
- Fix: repository/ref/path + events_sha256 + manifest_digest (intrinsic) only
- External retaining attestation: repository/ref/commit_sha/path (NOT in manifest)
- runtime=599c183, subject=79b5b5eb, GWC=68b45bd9 (gwc.git, read-only)
- W8 streak=0 (no fabricated W8-R3 execution)
