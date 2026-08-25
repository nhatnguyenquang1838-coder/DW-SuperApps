/**
 * DW-OBS-HIST-BACKFILL-R1 — historical Run backfill (DRY-RUN only).
 *
 * Reads authoritative repo evidence (fixtures + terminal-mailbox receipts) and
 * builds normalized rows for the 8 observatory tables. NEVER connects to
 * Supabase / NEVER applies DDL/DML. Output is a deterministic dry-run report
 * including a SCHEMA-AWARE constraint check (NOT NULL / CHECK enum / FK) that
 * mirrors the committed DDL, proving DML-vs-DDL validity locally.
 *
 * Remote apply gated behind exact G6 approval (supabase db push --linked
 * --include-all). This script is the offline validation artifact only.
 *
 * Determinism: reconstruction timestamp bound to a truthful, persisted value
 * (RECONSTRUCTION_META.json / env DW_OBS_RECONSTRUCTED_AT). Historical
 * timestamps use real evidence (PR mergedAt, CI createdAt, issue createdAt,
 * terminal-mailbox receipts). No invented midnights.
 */
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

const PROJECT_ROOT = process.env.DW_OBS_PROJECT_ROOT
  ? path.resolve(process.env.DW_OBS_PROJECT_ROOT)
  : process.cwd();
const FIXTURES = path.join(PROJECT_ROOT, "fixtures");
const META_PATH = path.join(PROJECT_ROOT, "..", "..", ".gwc", "tasks", "SCRUM-555", "history-backfill", "RECONSTRUCTION_META.json");

function resolvedReconstructedAt(): string {
  const env = process.env.DW_OBS_RECONSTRUCTED_AT;
  if (env) return env;
  try {
    const meta = JSON.parse(fs.readFileSync(META_PATH, "utf8"));
    if (meta.reconstructed_at) return meta.reconstructed_at;
  } catch { /* meta absent */ }
  throw new Error("DW_OBS_RECONSTRUCTED_AT or RECONSTRUCTION_META.json required");
}
const RECONSTRUCTED_AT = resolvedReconstructedAt();

// Authoritative receipts (GitHub PR/issue/CI + terminal-mailbox #71-#73) -----
const EVIDENCE = {
  issue: {
    "70": "2026-08-20T17:48:15Z", "71": "2026-08-20T17:48:31Z", "72": "2026-08-20T18:48:48Z",
    "73": "2026-08-20T18:48:58Z", "74": "2026-08-20T18:49:08Z", "75": "2026-08-20T18:49:17Z",
  } as Record<string, string>,
  pr: {
    "76": { created: "2026-08-20T22:46:27Z", merged: "2026-08-21T13:59:19Z", head: "78171b5783278d680e3aef331fbb5b7fef4d63d0", base: "50a32124e826e6b4cfa36b0e315ab29d2672136a" },
    "77": { created: "2026-08-21T16:37:55Z", merged: "2026-08-21T18:38:13Z", head: "a94cf134c38c999daa63994b2b02d856078daee2", base: "79e6c485910f681ee0318ff7128eaa6971f8cc2a" },
    "78": { created: "2026-08-22T06:51:19Z", merged: "2026-08-22T16:55:25Z", head: "4e4ba62b686f9aa49b932c412ec67b80767ed80d", base: "22d2d416169aaa8c60a84651d7f01694a193adb3" },
    "79": { created: "2026-08-22T17:59:34Z", merged: "2026-08-22T18:06:04Z", head: "5e59c889039968f606d52906c5433a21a4751bd9", base: "edb91060017ea02685718a1fadf1dbb7acddbee7" },
  } as Record<string, { created: string; merged: string; head: string; base: string }>,
  ci: {
    "32477448758": { created: "2026-08-21T11:29:38Z", head: "78171b5783278d680e3aef331fbb5b7fef4d63d0", status: "SUCCESS" },
    "32513844239": { created: "2026-08-21T18:32:09Z", head: "a94cf134c38c999daa63994b2b02d856078daee2", status: "SUCCESS" },
    "32585204072": { created: "2026-08-22T16:36:12Z", head: "4e4ba62b686f9aa49b932c412ec67b80767ed80d", status: "SUCCESS" },
    "32589399526": { created: "2026-08-22T17:59:37Z", head: "5e59c889039968f606d52906c5433a21a4751bd9", status: "SUCCESS" },
  } as Record<string, { created: string; head: string; status: string }>,
  scopeHash: {
    "76": "5dc46c3b8bc69b89fde4edd958bf7a398974d806649a277d52789e62ed85116f",
    "77": "84f3326b8126d700cbff3aff84c9cf901aae31ba4b55081f80820c46f2e718d1",
    "79": "aa5756f5dfc424ba",
  } as Record<string, string>,
  mergeSha: {
    "76": "79e6c485910f681ee0318ff7128eaa6971f8cc2a",
    "77": "22d2d416169aaa8c60a84651d7f01694a193adb3",
    "78": "edb91060017ea02685718a1fadf1dbb7acddbee7",
    "79": "a992fa4824db17434f6bdf8aabe8d6f435cc5767",
  } as Record<string, string>,
  // terminal-mailbox receipts (authoritative issue threads + exact comment ids)
  mailbox: { "76": "71", "77": "72", "78": "73", "79": "70" } as Record<string, string>,
  mailboxComment: {
    "76": { id: "5370838035", ts: "2026-08-21T14:03:22Z", ref: "github:issue/71#issuecomment-5370838035" },
    "77": { id: "5370849202", ts: "2026-08-21T14:04:08Z", ref: "github:issue/72#issuecomment-5370849202" },
    "78": { id: "5373867605", ts: "2026-08-21T18:42:23Z", ref: "github:issue/73#issuecomment-5373867605" },
    "79": { id: "5381850075", ts: "2026-08-22T18:08:14Z", ref: "github:issue/70#issuecomment-5381850075" },
  } as Record<string, { id: string; ts: string; ref: string }>,
};

type RunKind = "observed_real" | "simulated_fixture" | "golden_fixture" | "reconstructed_history";
type SourceSystem = "taskcontroller" | "gwc" | "github" | "repo_governance";
type SourceKind =
  | "live_capture" | "golden_fixture" | "github_pr" | "github_issue"
  | "ci_run" | "gwc_artifact" | "reconstruction" | "repo_governance" | "controller_mailbox";
type ArtifactStatus = "original" | "reconstructed" | "missing_unreconstructable";

interface RunsRow {
  run_id: string; run_kind: RunKind; source_system: "taskcontroller" | "gwc" | "mixed";
  epic_id?: string; jira_key?: string; parent_issue?: string; authority_ref?: string;
  scope_hash?: string; base_sha?: string; head_sha?: string; merge_sha?: string;
  base_branch?: string; branch?: string; pr_number?: number;
  ci_run_id?: string; ci_status?: string; started_at?: string; completed_at?: string;
  reconstruction_basis?: string; source_refs: string[]; confidence?: "HIGH" | "PARTIAL" | "UNKNOWN";
  evidence_quality?: "STRONG" | "PARTIAL" | "WEAK" | "NONE"; reconstructed_by?: string; reconstructed_at?: string;
  payload: Record<string, unknown>;
}
interface ArtifactRow {
  artifact_id: string; run_id: string; node_id?: string; gate_id?: string;
  artifact_type: string; artifact_status: ArtifactStatus; original_artifact_present: boolean;
  source_occurred_at?: string; effective_at?: string; reconstructed_at?: string;
  reconstruction_basis?: string; source_refs: string[]; confidence?: "HIGH" | "PARTIAL" | "UNKNOWN";
  evidence_quality?: "STRONG" | "PARTIAL" | "WEAK" | "NONE"; reconstructed_by?: string;
  payload: Record<string, unknown>;
}
interface SourceRow {
  source_id: string; run_id: string; source_system: SourceSystem; source_event_id?: string;
  source_kind: SourceKind; capture_provenance_verified: boolean; source_ref?: string; source_digest?: string;
  occurred_at?: string; authority_ref?: string; evidence_refs: string[];
}
interface GateRow { gate_id: string; run_id: string; gate_label?: string; boundary?: string; authority_ref?: string; state?: string; summary?: string; node_count?: number; artifact_count?: number; source_refs: string[]; }
interface NodeRow { node_id: string; run_id: string; gate_id?: string; family?: string; boundary?: string; state?: string; label?: string; source_refs: string[]; }

function loadFixture(name: string): any {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

// ---- golden fixtures -> SOURCE rows (NOT separate runs) --------------------
function buildFixtureSources(): { sources: SourceRow[] } {
  const tc = loadFixture("run_scrum555_m0.json");
  const gwc = loadFixture("run_gwc_durable_m0.json");
  const sources: SourceRow[] = [];
  sources.push({
    source_id: `golden-${tc.run_id}`, run_id: tc.run_id, source_system: "taskcontroller",
    source_event_id: undefined, source_kind: "golden_fixture", capture_provenance_verified: false,
    source_ref: "fixtures/run_scrum555_m0.json", occurred_at: undefined,
    authority_ref: "G2-DW-OBS-M0-20260821-R2",
    evidence_refs: [`PR #76 (M0 contract: Golden fixtures + replay tests)`, `source_run_id=${tc.run_id}`],
  });
  sources.push({
    source_id: `golden-${gwc.run_id}`, run_id: tc.run_id, source_system: "gwc",
    source_event_id: undefined, source_kind: "golden_fixture", capture_provenance_verified: false,
    source_ref: "fixtures/run_gwc_durable_m0.json", occurred_at: undefined,
    authority_ref: "G2_EXECUTION",
    evidence_refs: [`PR #76 (M0 contract: Golden fixtures + replay tests)`, `source_run_id=${gwc.run_id}`],
  });
  return { sources };
}

// ---- reconstructed_history runs (exact receipts only) ----------------------
interface ReconDef {
  run_id: string; approval_id: string; pr_number: number; issue: string;
  gate_id?: string; nodes?: string[]; ci_run_id: string; milestone: string; has_alignment_scope: boolean;
  scope_hash?: string; base_sha?: string; head_sha?: string; merge_sha?: string; branch?: string;
}
const RECONSTRUCTED: ReconDef[] = [
  {
    run_id: "DW-OBS-M0-20260821-R2", approval_id: "G2-DW-OBS-M0-20260821-R2", pr_number: 76, issue: "71",
    gate_id: "G2-DW-OBS-M0-20260821-R2", nodes: ["71"], milestone: "M0", has_alignment_scope: true,
    scope_hash: EVIDENCE.scopeHash["76"], base_sha: EVIDENCE.pr["76"].base, head_sha: EVIDENCE.pr["76"].head,
    merge_sha: EVIDENCE.mergeSha["76"], branch: "auto/SCRUM-555-dw-observation-m0-r2", ci_run_id: "32477448758",
  },
  {
    run_id: "DW-OBS-M1-20260821-R1", approval_id: "G2-DW-OBS-M1-20260821-R1", pr_number: 77, issue: "72",
    gate_id: "G2-DW-OBS-M1-20260821-R1", milestone: "M1", has_alignment_scope: true,
    scope_hash: EVIDENCE.scopeHash["77"], base_sha: EVIDENCE.pr["77"].base, head_sha: EVIDENCE.pr["77"].head,
    merge_sha: EVIDENCE.mergeSha["77"], branch: "auto/SCRUM-555-dw-observation-m1-r1", ci_run_id: "32513844239",
  },
  {
    run_id: "DW-OBS-M2-20260822-R1", approval_id: "G2-DW-OBS-M2-20260822-R1", pr_number: 78, issue: "73",
    milestone: "M2", has_alignment_scope: true, base_sha: EVIDENCE.pr["78"].base, head_sha: EVIDENCE.pr["78"].head,
    merge_sha: EVIDENCE.mergeSha["78"], branch: "auto/SCRUM-555-dw-observation-m2-r1", ci_run_id: "32585204072",
  },
  {
    run_id: "DW-OBS-M3M4-20260823-R1", approval_id: "G2-DW-OBS-M3M4-20260823-R1", pr_number: 79, issue: "70",
    gate_id: "G2-DW-OBS-M3M4-20260823-R1", nodes: ["74", "75"], milestone: "M3/M4", has_alignment_scope: true,
    scope_hash: EVIDENCE.scopeHash["79"], base_sha: EVIDENCE.pr["79"].base, head_sha: EVIDENCE.pr["79"].head,
    merge_sha: EVIDENCE.mergeSha["79"], branch: "auto/SCRUM-555-dw-observation-m3m4-r1", ci_run_id: "32589399526",
  },
];

function buildReconstructed(): { runs: RunsRow[]; gates: GateRow[]; nodes: NodeRow[]; sources: SourceRow[]; artifacts: ArtifactRow[] } {
  const runs: RunsRow[] = []; const gates: GateRow[] = []; const nodes: NodeRow[] = [];
  const sources: SourceRow[] = []; const artifacts: ArtifactRow[] = [];
  const evidencePath = ".gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md";
  let evidenceDigest: string | undefined;
  try {
    const abs = path.resolve(PROJECT_ROOT, "..", "..", evidencePath);
    evidenceDigest = crypto.createHash("sha256").update(fs.readFileSync(abs)).digest("hex");
  } catch { evidenceDigest = undefined; }

  for (const d of RECONSTRUCTED) {
    const pr = EVIDENCE.pr[String(d.pr_number)];
    const iss = EVIDENCE.issue[d.issue];
    const mergedAt = pr.merged;
    const ci = EVIDENCE.ci[d.ci_run_id];
    const mailboxIssue = EVIDENCE.mailbox[String(d.pr_number)];
    const mb = EVIDENCE.mailboxComment[String(d.pr_number)];

    runs.push({
      run_id: d.run_id, run_kind: "reconstructed_history", source_system: "taskcontroller",
      jira_key: "SCRUM-555", parent_issue: d.issue, authority_ref: d.approval_id,
      scope_hash: d.scope_hash, base_sha: d.base_sha, head_sha: d.head_sha, merge_sha: d.merge_sha,
      base_branch: "pre-prod", branch: d.branch, pr_number: d.pr_number, ci_run_id: d.ci_run_id,
      ci_status: ci?.status, started_at: pr.created, completed_at: mergedAt,
      reconstruction_basis: `PR #${d.pr_number} (merged ${mergedAt}) + terminal mailbox ${mb.ref}`,
      source_refs: [`github:pull/${d.pr_number}`, `github:issue/${mailboxIssue}`, mb.ref, `github:actions:run/${d.ci_run_id}`],
      confidence: "HIGH", evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes", reconstructed_at: RECONSTRUCTED_AT,
      payload: { milestone: d.milestone, approval_id: d.approval_id },
    });

    // normalized sources: github_pr, github_issue (generic, issue-created ts), ci_run, reconstruction, controller_mailbox (exact comment)
    sources.push({
      source_id: `pr-${d.run_id}`, run_id: d.run_id, source_system: "github", source_kind: "github_pr",
      capture_provenance_verified: true, source_ref: `github:pull/${d.pr_number}`, occurred_at: mergedAt,
      evidence_refs: [`PR #${d.pr_number} merged ${mergedAt}`],
    });
    sources.push({
      source_id: `issue-${d.run_id}`, run_id: d.run_id, source_system: "github", source_kind: "github_issue",
      capture_provenance_verified: true, source_ref: `github:issue/${mailboxIssue}`, occurred_at: iss,
      evidence_refs: [`issue #${mailboxIssue} created ${iss}`],
    });
    sources.push({
      source_id: `ci-${d.run_id}`, run_id: d.run_id, source_system: "github", source_kind: "ci_run",
      capture_provenance_verified: true, source_ref: `github:actions:run/${d.ci_run_id}`, occurred_at: ci?.created,
      evidence_refs: [`CI run ${d.ci_run_id} ${ci?.status} @ ${ci?.head}`],
    });
    sources.push({
      source_id: `recon-${d.run_id}`, run_id: d.run_id, source_system: "repo_governance", source_kind: "reconstruction",
      capture_provenance_verified: false, source_ref: ".gwc/tasks/SCRUM-555/history-backfill/RECONSTRUCTION.md",
      occurred_at: RECONSTRUCTED_AT, evidence_refs: [`PR #${d.pr_number}`, `issue #${mailboxIssue}`],
    });
    sources.push({
      source_id: `mailbox-${d.run_id}`, run_id: d.run_id, source_system: "github",
      source_kind: "controller_mailbox", capture_provenance_verified: true,
      source_ref: mb.ref, occurred_at: mb.ts,
      authority_ref: d.approval_id,
      evidence_refs: [
        `terminal mailbox comment ${mb.ref}`,
        `run_id=${d.run_id}`, `approval_id=${d.approval_id}`,
        `scope_hash=${d.scope_hash ?? "n/a"}`, `head_sha=${d.head_sha}`,
        `ci_run=${d.ci_run_id}`, `merge_sha=${d.merge_sha}`,
      ],
    });

    if (d.gate_id) {
      gates.push({
        gate_id: d.gate_id, run_id: d.run_id, gate_label: d.gate_id, authority_ref: d.approval_id,
        state: "passed", summary: `G2 authority for ${d.run_id}`,
        node_count: d.nodes?.length ?? 0, artifact_count: 0,
        source_refs: [`github:pull/${d.pr_number}`, `github:issue/${mailboxIssue}`, `github:actions:run/${d.ci_run_id}`],
      });
    }
    for (const n of d.nodes ?? []) {
      nodes.push({
        node_id: n, run_id: d.run_id, gate_id: d.gate_id, state: "done", label: `node ${n}`,
        source_refs: [`github:issue/${mailboxIssue}`],
      });
    }

    // Artifacts: context->issue ts; delivery->PR merge ts; CI->CI run ts (real, all runs); alignment->PR merge ts
    const ciRefs = [`github:actions:run/${d.ci_run_id}`, `github:issue/${mailboxIssue}`, mb.ref];
    const baseArts: Array<Pick<ArtifactRow, "artifact_type" | "reconstruction_basis" | "source_occurred_at" | "source_refs" | "confidence" | "evidence_quality">> = [
      {
        artifact_type: "reconstructed_context_evidence",
        reconstruction_basis: `Reconstructed from terminal mailbox issue #${mailboxIssue} context (created ${iss})`,
        source_occurred_at: iss, source_refs: [`github:issue/${mailboxIssue}`], confidence: "HIGH", evidence_quality: "STRONG",
      },
      {
        artifact_type: "reconstructed_delivery_record",
        reconstruction_basis: `Reconstructed from PR #${d.pr_number} merge record (merged ${mergedAt})`,
        source_occurred_at: mergedAt, source_refs: [`github:pull/${d.pr_number}`, `github:issue/${mailboxIssue}`], confidence: "HIGH", evidence_quality: "STRONG",
      },
      {
        artifact_type: "reconstructed_ci_evidence",
        reconstruction_basis: `Reconstructed from CI run ${d.ci_run_id} (${ci?.status} @ ${ci?.head}, ${ci?.created})`,
        source_occurred_at: ci?.created, source_refs: ciRefs, confidence: "HIGH", evidence_quality: "STRONG",
      },
    ];
    if (d.has_alignment_scope) {
      baseArts.push({
        artifact_type: "reconstructed_alignment_scope",
        reconstruction_basis: `Reconstructed gate alignment scope (scope_hash ${d.scope_hash ?? "n/a"}) from PR #${d.pr_number} + mailbox #${mailboxIssue}`,
        source_occurred_at: mergedAt, source_refs: [`github:pull/${d.pr_number}`, `github:issue/${mailboxIssue}`], confidence: "HIGH", evidence_quality: "STRONG",
      });
    }
    for (const a of baseArts) {
      artifacts.push({
        artifact_id: `${d.run_id}:${a.artifact_type}`, run_id: d.run_id, artifact_type: a.artifact_type,
        artifact_status: "reconstructed", original_artifact_present: false,
        source_occurred_at: a.source_occurred_at, effective_at: mergedAt, reconstructed_at: RECONSTRUCTED_AT,
        reconstruction_basis: a.reconstruction_basis, source_refs: a.source_refs, confidence: a.confidence,
        evidence_quality: a.evidence_quality, reconstructed_by: "TaskController/Hermes", payload: { milestone: d.milestone },
      });
    }

    // M3M4 only: original evidence file artifact + repo_governance source row
    if (d.run_id === "DW-OBS-M3M4-20260823-R1") {
      sources.push({
        source_id: `evidence-DW-OBS-M3M4-20260823-R1`, run_id: d.run_id, source_system: "repo_governance",
        source_kind: "repo_governance", capture_provenance_verified: true, source_ref: evidencePath,
        source_digest: evidenceDigest, occurred_at: undefined, evidence_refs: [evidencePath],
      });
      artifacts.push({
        artifact_id: `${d.run_id}:M3-M4-EVIDENCE.md`, run_id: d.run_id, artifact_type: "historical_evidence_file",
        artifact_status: "original", original_artifact_present: true, source_occurred_at: undefined,
        effective_at: mergedAt, reconstruction_basis: "Real persisted historical file referenced by evidence",
        source_refs: [evidencePath], confidence: "HIGH", evidence_quality: "STRONG",
        reconstructed_by: "TaskController/Hermes", payload: { repo_ref: evidencePath, digest: evidenceDigest },
      });
    }
  }
  return { runs, gates, nodes, sources, artifacts };
}

// ---- validation -----------------------------------------------------------
interface DryRunReport {
  ok: boolean; counts: Record<string, number>; byRunKind: Record<string, number>;
  byArtifactStatus: Record<string, number>; artifactStatusByRun: Record<string, Record<string, number>>;
  upsertKeyConflicts: string[]; duplicateRunRows: string[]; realVsSimSeparation: boolean;
  riChecks: string[]; provenanceChecks: string[]; schemaChecks: string[]; rollback: string;
  errors: string[]; digest: string;
}
function digestOf(obj: unknown): string {
  return crypto.createHash("sha256").update(JSON.stringify(obj)).digest("hex");
}
function validate(
  runs: RunsRow[], events: any[], gates: GateRow[], nodes: NodeRow[],
  sources: SourceRow[], artifacts: ArtifactRow[],
): DryRunReport {
  const errors: string[] = []; const upsertKeyConflicts: string[] = []; const duplicateRunRows: string[] = [];
  const riChecks: string[] = []; const provenanceChecks: string[] = []; const schemaChecks: string[] = [];

  const seen = new Set<string>();
  for (const r of runs) { if (seen.has(r.run_id)) duplicateRunRows.push(r.run_id); seen.add(r.run_id); }
  const evKeys = new Set<string>();
  for (const e of events) {
    const k = `${e.run_id}|${e.source_system}|${e.source_event_id}`;
    if (evKeys.has(k)) upsertKeyConflicts.push(k); evKeys.add(k);
  }
  const byRunKind: Record<string, number> = {};
  for (const r of runs) byRunKind[r.run_kind] = (byRunKind[r.run_kind] || 0) + 1;
  const realVsSimSeparation = (byRunKind["observed_real"] || 0) === 0;

  const runIds = new Set(runs.map((r) => r.run_id));
  for (const e of events) if (!runIds.has(e.run_id)) riChecks.push(`event ${e.source_event_id} -> missing run ${e.run_id}`);
  for (const g of gates) if (!runIds.has(g.run_id)) riChecks.push(`gate ${g.gate_id} -> missing run ${g.run_id}`);
  for (const n of nodes) if (!runIds.has(n.run_id)) riChecks.push(`node ${n.node_id} -> missing run ${n.run_id}`);
  for (const s of sources) if (!runIds.has(s.run_id)) riChecks.push(`source ${s.source_id} -> missing run ${s.run_id}`);
  for (const a of artifacts) if (!runIds.has(a.run_id)) riChecks.push(`artifact ${a.artifact_id} -> missing run ${a.run_id}`);

  for (const r of runs) {
    if (r.run_kind === "reconstructed_history" && !sources.some((s) => s.run_id === r.run_id))
      provenanceChecks.push(`reconstructed run ${r.run_id} has no run_sources row`);
  }
  for (const a of artifacts) {
    const validRefs = new Set(sources.filter((s) => s.run_id === a.run_id).map((s) => s.source_ref).filter(Boolean) as string[]);
    for (const ref of a.source_refs) if (!validRefs.has(ref))
      provenanceChecks.push(`artifact ${a.artifact_id} ref '${ref}' does not resolve to a run_sources row of run ${a.run_id}`);
    if (a.source_refs.length === 0) provenanceChecks.push(`artifact ${a.artifact_id} has no source_refs`);
  }

  // Schema-aware constraint checks (mirror committed DDL) -------------------
  const RUN_KIND = ["observed_real","simulated_fixture","golden_fixture","reconstructed_history"];
  const SRC_SYS = ["taskcontroller","gwc","github","repo_governance"];
  const SRC_KIND = ["live_capture","golden_fixture","github_pr","github_issue","ci_run","gwc_artifact","reconstruction","repo_governance","controller_mailbox"];
  const ART_STATUS = ["original","reconstructed","missing_unreconstructable"];
  const CONF = ["HIGH","PARTIAL","UNKNOWN"];
  const EQ = ["STRONG","PARTIAL","WEAK","NONE"];
  const gateIds = new Set(gates.map((g) => g.gate_id));
  for (const r of runs) {
    if (!RUN_KIND.includes(r.run_kind)) schemaChecks.push(`runs ${r.run_id} run_kind invalid: ${r.run_kind}`);
    if (!SRC_SYS.includes(r.source_system)) schemaChecks.push(`runs ${r.run_id} source_system invalid: ${r.source_system}`);
    if (r.confidence && !CONF.includes(r.confidence)) schemaChecks.push(`runs ${r.run_id} confidence invalid`);
    if (r.evidence_quality && !EQ.includes(r.evidence_quality)) schemaChecks.push(`runs ${r.run_id} evidence_quality invalid`);
  }
  for (const e of events) {
    if (e.occurred_at == null) schemaChecks.push(`run_events ${e.source_event_id} occurred_at NOT NULL violated`);
    if (!SRC_SYS.includes(e.source_system)) schemaChecks.push(`run_events ${e.source_event_id} source_system invalid`);
  }
  for (const g of gates) {
    if (!g.gate_id) schemaChecks.push(`run_gates gate_id NOT NULL violated`);
    if (!runIds.has(g.run_id)) schemaChecks.push(`run_gates ${g.gate_id} FK run missing`);
  }
  for (const n of nodes) {
    if (!n.node_id) schemaChecks.push(`run_nodes node_id NOT NULL violated`);
    if (!runIds.has(n.run_id)) schemaChecks.push(`run_nodes ${n.node_id} FK run missing`);
    if (n.gate_id && !gateIds.has(n.gate_id)) schemaChecks.push(`run_nodes ${n.node_id} FK gate ${n.gate_id} missing (nullable FK ok if null)`);
  }
  for (const s of sources) {
    if (!SRC_SYS.includes(s.source_system)) schemaChecks.push(`run_sources ${s.source_id} source_system invalid: ${s.source_system}`);
    if (!SRC_KIND.includes(s.source_kind)) schemaChecks.push(`run_sources ${s.source_id} source_kind invalid: ${s.source_kind}`);
  }
  for (const a of artifacts) {
    if (!ART_STATUS.includes(a.artifact_status)) schemaChecks.push(`run_artifacts ${a.artifact_id} artifact_status invalid`);
    if (a.confidence && !CONF.includes(a.confidence)) schemaChecks.push(`run_artifacts ${a.artifact_id} confidence invalid`);
    if (a.evidence_quality && !EQ.includes(a.evidence_quality)) schemaChecks.push(`run_artifacts ${a.artifact_id} evidence_quality invalid`);
  }

  const byArtifactStatus: Record<string, number> = {};
  const artifactStatusByRun: Record<string, Record<string, number>> = {};
  for (const a of artifacts) {
    byArtifactStatus[a.artifact_status] = (byArtifactStatus[a.artifact_status] || 0) + 1;
    artifactStatusByRun[a.run_id] = artifactStatusByRun[a.run_id] || {};
    artifactStatusByRun[a.run_id][a.artifact_status] = (artifactStatusByRun[a.run_id][a.artifact_status] || 0) + 1;
  }
  const counts: Record<string, number> = {
    runs: runs.length, events: events.length, gates: gates.length, nodes: nodes.length,
    artifacts: artifacts.length, checkpoints: 0, edges: 0, sources: sources.length,
  };
  if (duplicateRunRows.length) errors.push(`duplicate run rows: ${duplicateRunRows.join(", ")}`);
  if (upsertKeyConflicts.length) errors.push(`event upsert conflicts: ${upsertKeyConflicts.length}`);
  if (riChecks.length) errors.push(`RI violations: ${riChecks.length}`);
  if (!realVsSimSeparation) errors.push(`observed_real=${byRunKind["observed_real"]} (expected 0)`);
  if (provenanceChecks.length) errors.push(`provenance violations: ${provenanceChecks.length}`);
  if (schemaChecks.length) errors.push(`schema constraint violations: ${schemaChecks.length}`);
  return {
    ok: errors.length === 0, counts, byRunKind, byArtifactStatus, artifactStatusByRun,
    upsertKeyConflicts, duplicateRunRows, realVsSimSeparation, riChecks, provenanceChecks, schemaChecks,
    rollback: `DROP TABLE IF EXISTS run_sources, run_edges, run_checkpoints, run_artifacts, run_events, run_nodes, run_gates, runs CASCADE;`,
    errors, digest: digestOf({ runs, events, gates, nodes, sources, artifacts }),
  };
}

// ---- deterministic DML emission -------------------------------------------
function sqlStr(v: unknown): string {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  return `'${String(v).replace(/'/g, "''")}'`;
}
function sqlArr(arr: string[]): string {
  if (!arr || arr.length === 0) return "'{}'";
  return `'{${arr.map((x) => `"${x.replace(/"/g, '\\"')}"`).join(",")}}'`;
}
function emitDML(runs: RunsRow[], events: any[], gates: GateRow[], nodes: NodeRow[], sources: SourceRow[], artifacts: ArtifactRow[]): string {
  const L: string[] = [];
  L.push(`-- DW-OBS-HIST-BACKFILL-R1 · deterministic backfill DML (idempotent ON CONFLICT DO NOTHING)`);
  L.push(`-- Applied by 'supabase db push --linked --include-all' once committed under supabase/migrations.`);
  L.push(`BEGIN;`);
  for (const r of runs) {
    L.push(`INSERT INTO runs (run_id,run_kind,source_system,epic_id,jira_key,parent_issue,authority_ref,scope_hash,base_sha,head_sha,merge_sha,base_branch,branch,pr_number,ci_run_id,ci_status,started_at,completed_at,reconstruction_basis,source_refs,confidence,evidence_quality,reconstructed_by,reconstructed_at,payload) VALUES (` +
      [sqlStr(r.run_id), sqlStr(r.run_kind), sqlStr(r.source_system), sqlStr(r.epic_id), sqlStr(r.jira_key), sqlStr(r.parent_issue), sqlStr(r.authority_ref), sqlStr(r.scope_hash), sqlStr(r.base_sha), sqlStr(r.head_sha), sqlStr(r.merge_sha), sqlStr(r.base_branch), sqlStr(r.branch), sqlStr(r.pr_number), sqlStr(r.ci_run_id), sqlStr(r.ci_status), sqlStr(r.started_at), sqlStr(r.completed_at), sqlStr(r.reconstruction_basis), sqlArr(r.source_refs), sqlStr(r.confidence), sqlStr(r.evidence_quality), sqlStr(r.reconstructed_by), sqlStr(r.reconstructed_at), `'{}'::jsonb`].join(",") +
      `) ON CONFLICT (run_id) DO NOTHING;`);
  }
  for (const g of gates) {
    L.push(`INSERT INTO run_gates (gate_id,run_id,gate_label,boundary,authority_ref,state,summary,node_count,artifact_count,source_refs) VALUES (` +
      [sqlStr(g.gate_id), sqlStr(g.run_id), sqlStr(g.gate_label), sqlStr(g.boundary), sqlStr(g.authority_ref), sqlStr(g.state), sqlStr(g.summary), sqlStr(g.node_count), sqlStr(g.artifact_count), sqlArr(g.source_refs)].join(",") +
      `) ON CONFLICT (gate_id) DO NOTHING;`);
  }
  for (const n of nodes) {
    L.push(`INSERT INTO run_nodes (node_id,run_id,gate_id,family,boundary,state,label,source_refs) VALUES (` +
      [sqlStr(n.node_id), sqlStr(n.run_id), sqlStr(n.gate_id), sqlStr(n.family), sqlStr(n.boundary), sqlStr(n.state), sqlStr(n.label), sqlArr(n.source_refs)].join(",") +
      `) ON CONFLICT (node_id) DO NOTHING;`);
  }
  for (const s of sources) {
    L.push(`INSERT INTO run_sources (source_id,run_id,source_system,source_event_id,source_kind,capture_provenance_verified,source_ref,source_digest,occurred_at,authority_ref,evidence_refs) VALUES (` +
      [sqlStr(s.source_id), sqlStr(s.run_id), sqlStr(s.source_system), sqlStr(s.source_event_id), sqlStr(s.source_kind), sqlStr(s.capture_provenance_verified), sqlStr(s.source_ref), sqlStr(s.source_digest), sqlStr(s.occurred_at), sqlStr(s.authority_ref), sqlArr(s.evidence_refs)].join(",") +
      `) ON CONFLICT (run_id,source_id) DO NOTHING;`);
  }
  for (const a of artifacts) {
    L.push(`INSERT INTO run_artifacts (artifact_id,run_id,artifact_type,artifact_status,original_artifact_present,source_occurred_at,effective_at,reconstructed_at,reconstruction_basis,source_refs,confidence,evidence_quality,reconstructed_by,payload) VALUES (` +
      [sqlStr(a.artifact_id), sqlStr(a.run_id), sqlStr(a.artifact_type), sqlStr(a.artifact_status), sqlStr(a.original_artifact_present), sqlStr(a.source_occurred_at), sqlStr(a.effective_at), sqlStr(a.reconstructed_at), sqlStr(a.reconstruction_basis), sqlArr(a.source_refs), sqlStr(a.confidence), sqlStr(a.evidence_quality), sqlStr(a.reconstructed_by), `'{}'::jsonb`].join(",") +
      `) ON CONFLICT (artifact_id) DO NOTHING;`);
  }
  L.push(`COMMIT;`);
  return L.join("\n");
}

function main() {
  const fix = buildFixtureSources();
  const rec = buildReconstructed();
  const allRuns = rec.runs;
  const allSources = [...fix.sources, ...rec.sources];
  const report = validate(allRuns, [], rec.gates, rec.nodes, allSources, rec.artifacts);
  if (process.env.DW_OBS_EMIT_DML) {
    process.stdout.write(emitDML(allRuns, [], rec.gates, rec.nodes, allSources, rec.artifacts));
    process.exit(0);
  }
  console.log(JSON.stringify({
    migration_ddl: "20260823080000_observatory_history.sql",
    migration_dml: "20260823090000_observatory_backfill_dml.sql",
    target_project: "auswvdxoetufwiaxutib", dry_run: true, remote_apply: false,
    apply_path: "supabase db push --linked --include-all (committed migration; no separate psql)",
    g6_boundary: "STOP — no remote apply until exact G6 approval bound",
    reconstructed_at: RECONSTRUCTED_AT, ...report, runs: allRuns,
    note_events: "run_events=0: golden fixture events are NOT canonical live events (seq=11).",
  }, null, 2));
  process.exit(report.ok ? 0 : 1);
}
main();
