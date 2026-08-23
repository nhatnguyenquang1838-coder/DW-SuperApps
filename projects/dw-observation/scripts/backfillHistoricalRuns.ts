/**
 * DW-OBS-HIST-BACKFILL-R1 — historical Run backfill (DRY-RUN only).
 *
 * Reads authoritative repo evidence (fixtures + inventory) and builds the
 * normalized row sets for the 8 observatory tables. NEVER connects to
 * Supabase and NEVER applies DDL/DML. Output is a deterministic dry-run
 * report (row counts, idempotency/upsert-key checks, RI checks, provenance
 * checks, reconstruction provenance, deterministic digest).
 *
 * Remote apply is gated behind exact G6 approval. This script is the offline
 * validation artifact only. The apply path is a separate deterministic DML
 * migration (supabase/migrations/20260823T090000Z_observatory_backfill_dml.sql)
 * applied only after G6 via `supabase db push --linked --include-all`
 * (no separate psql step).
 *
 * Determinism: reconstruction timestamp is bound to a truthful, persisted
 * value (RECONSTRUCTION_META.json / env DW_OBS_RECONSTRUCTED_AT), captured
 * during the actual governed run. No invented future/rounded timestamps.
 * Historical event times use real evidence timestamps (GitHub PR mergedAt,
 * CI run createdAt, issue createdAt) — never hand-authored midnights.
 */
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

const PROJECT_ROOT = process.env.DW_OBS_PROJECT_ROOT
  ? path.resolve(process.env.DW_OBS_PROJECT_ROOT)
  : process.cwd();
const FIXTURES = path.join(PROJECT_ROOT, "fixtures");
const META_PATH = path.join(PROJECT_ROOT, "..", "..", ".gwc", "tasks", "SCRUM-555", "history-backfill", "RECONSTRUCTION_META.json");

// Truthful reconstruction timestamp, persisted by the governed run.
function resolvedReconstructedAt(): string {
  const env = process.env.DW_OBS_RECONSTRUCTED_AT;
  if (env) return env;
  try {
    const meta = JSON.parse(fs.readFileSync(META_PATH, "utf8"));
    if (meta.reconstructed_at) return meta.reconstructed_at;
  } catch {
    /* meta not present */
  }
  throw new Error("DW_OBS_RECONSTRUCTED_AT or RECONSTRUCTION_META.json required for deterministic truthful timestamp");
}
const RECONSTRUCTED_AT = resolvedReconstructedAt();

// ---- Authoritative evidence timestamps (from GitHub, real, not invented) ----
// Source: gh pr view / gh issue view / gh run view, captured for this run.
const EVIDENCE = {
  // issues createdAt
  issue: {
    "70": "2026-08-20T17:48:15Z",
    "71": "2026-08-20T17:48:31Z",
    "72": "2026-08-20T18:48:48Z",
    "73": "2026-08-20T18:48:58Z",
    "74": "2026-08-20T18:49:08Z",
    "75": "2026-08-20T18:49:17Z",
  } as Record<string, string>,
  // PRs: createdAt / mergedAt / headSha
  pr: {
    "76": { created: "2026-08-20T22:46:27Z", merged: "2026-08-21T13:59:19Z", head: "78171b5783278d680e3aef331fbb5b7fef4d63d0" },
    "77": { created: "2026-08-21T16:37:55Z", merged: "2026-08-21T18:38:13Z", head: "a94cf134c38c999daa63994b2b02d856078daee2" },
    "78": { created: "2026-08-22T06:51:19Z", merged: "2026-08-22T16:55:25Z", head: "4e4ba62b686f9aa49b932c412ec67b80767ed80d" },
    "79": { created: "2026-08-22T17:59:34Z", merged: "2026-08-22T18:06:04Z", head: "5e59c889039968f606d52906c5433a21a4751bd9" },
  } as Record<string, { created: string; merged: string; head: string }>,
  // CI runs: runId / createdAt / headSha
  ci: {
    // M3/M4 exact approved head 5e59c889... → Validate workspace #32589399526
    "32589399526": { created: "2026-08-22T17:59:37Z", head: "5e59c889039968f606d52906c5433a21a4751bd9", status: "SUCCESS" },
  } as Record<string, { created: string; head: string; status: string }>,
};

type RunKind = "observed_real" | "simulated_fixture" | "golden_fixture" | "reconstructed_history";
type SourceSystem = "taskcontroller" | "gwc" | "github" | "repo_governance";
type SourceKind =
  | "live_capture"
  | "golden_fixture"
  | "github_pr"
  | "github_issue"
  | "ci_run"
  | "gwc_artifact"
  | "reconstruction"
  | "repo_governance";
type ArtifactStatus = "original" | "reconstructed" | "missing_unreconstructable";

interface RunsRow {
  run_id: string;
  run_kind: RunKind;
  source_system: "taskcontroller" | "gwc" | "mixed";
  epic_id?: string;
  jira_key?: string;
  parent_issue?: string;
  authority_ref?: string;
  scope_sha?: string;
  base_branch?: string;
  branch?: string;
  pr_number?: number;
  ci_run_id?: string;
  ci_status?: string;
  started_at?: string;
  completed_at?: string;
  reconstruction_basis?: string;
  source_refs: string[];
  confidence?: "HIGH" | "PARTIAL" | "UNKNOWN";
  evidence_quality?: "STRONG" | "PARTIAL" | "WEAK" | "NONE";
  reconstructed_by?: string;
  reconstructed_at?: string;
  payload: Record<string, unknown>;
}

interface ArtifactRow {
  artifact_id: string;
  run_id: string;
  node_id?: string;
  gate_id?: string;
  artifact_type: string;
  artifact_status: ArtifactStatus;
  original_artifact_present: boolean;
  source_occurred_at?: string;
  effective_at?: string;
  reconstructed_at?: string;
  reconstruction_basis?: string;
  source_refs: string[];
  confidence?: "HIGH" | "PARTIAL" | "UNKNOWN";
  evidence_quality?: "STRONG" | "PARTIAL" | "WEAK" | "NONE";
  reconstructed_by?: string;
  payload: Record<string, unknown>;
}

interface SourceRow {
  source_id: string;
  run_id: string;
  source_system: SourceSystem;
  source_event_id?: string;
  source_kind: SourceKind;
  capture_provenance_verified: boolean;
  source_ref?: string;
  source_digest?: string;
  occurred_at?: string;
  authority_ref?: string;
  evidence_refs: string[];
}

// ---- loaders ---------------------------------------------------------------
function loadFixture(name: string): any {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

// ---- golden/simulated fixtures → golden_fixture runs + supporting sources ---
function buildFixtureRuns(): { runs: RunsRow[]; events: any[]; gates: any[]; nodes: any[]; sources: SourceRow[] } {
  const out: RunsRow[] = [];
  const events: any[] = [];
  const gates: any[] = [];
  const nodes: any[] = [];
  const sources: SourceRow[] = [];

  const tc = loadFixture("run_scrum555_m0.json");
  const gwc = loadFixture("run_gwc_durable_m0.json");
  const projTc = loadFixture("projection_scrum555_m0.json");
  const projGwc = loadFixture("projection_gwc_durable_m0.json");

  out.push({
    run_id: tc.run_id,
    run_kind: "golden_fixture",
    source_system: "taskcontroller",
    jira_key: "SCRUM-555",
    parent_issue: "70",
    payload: { source: "fixtures/run_scrum555_m0.json", events: tc.events.length, note: "golden fixture, not live capture" },
    source_refs: ["fixtures/run_scrum555_m0.json"],
  });
  out.push({
    run_id: gwc.run_id,
    run_kind: "golden_fixture",
    source_system: "gwc",
    payload: { source: "fixtures/run_gwc_durable_m0.json", events: gwc.events.length, note: "golden fixture, not live capture" },
    source_refs: ["fixtures/run_gwc_durable_m0.json"],
  });

  for (const e of tc.events as any[]) {
    events.push(Object.assign({}, e, {
      run_id: tc.run_id,
      source_system: e.source ?? "taskcontroller",
      source_event_id: e.event_id,
      event_type: e.event_type ?? e.decision_kind ?? "unknown",
    }));
  }
  for (const e of gwc.events as any[]) {
    events.push(Object.assign({}, e, {
      run_id: gwc.run_id,
      source_system: e.source ?? "gwc",
      source_event_id: e.event_id,
      event_type: e.event_type ?? e.decision_kind ?? "unknown",
    }));
  }

  const projTcGates = projTc.gates && typeof projTc.gates === "object" ? Object.values(projTc.gates) : [];
  const projTcNodes = projTc.nodes && typeof projTc.nodes === "object" ? Object.values(projTc.nodes) : [];
  const projGwcGates = projGwc.gates && typeof projGwc.gates === "object" ? Object.values(projGwc.gates) : [];
  const projGwcNodes = projGwc.nodes && typeof projGwc.nodes === "object" ? Object.values(projGwc.nodes) : [];

  for (const g of projTcGates as any[]) gates.push(Object.assign({}, g, { run_id: tc.run_id }));
  for (const n of projTcNodes as any[]) nodes.push(Object.assign({}, n, { run_id: tc.run_id }));
  for (const g of projGwcGates as any[]) gates.push(Object.assign({}, g, { run_id: gwc.run_id }));
  for (const n of projGwcNodes as any[]) nodes.push(Object.assign({}, n, { run_id: gwc.run_id }));

  sources.push({
    source_id: `src-${tc.run_id}`,
    run_id: tc.run_id,
    source_system: "taskcontroller",
    source_kind: "golden_fixture",
    capture_provenance_verified: false,
    source_ref: "fixtures/run_scrum555_m0.json",
    evidence_refs: ["PR #76 (M0 contract: Golden fixtures + replay tests)"],
  });
  sources.push({
    source_id: `src-${gwc.run_id}`,
    run_id: gwc.run_id,
    source_system: "gwc",
    source_kind: "golden_fixture",
    capture_provenance_verified: false,
    source_ref: "fixtures/run_gwc_durable_m0.json",
    evidence_refs: ["PR #76 (M0 contract: Golden fixtures + replay tests)"],
  });
  return { runs: out, events, gates, nodes, sources };
}

// ---- reconstructed_history → milestone delivery runs + sources + artifacts --
interface ReconstructedDef {
  run_id: string;
  pr_number: number;
  issue: string;
  authority_ref?: string;
  scope_sha?: string;
  branch?: string;
  ci_run_id?: string;
  milestone: string;
  has_alignment_scope: boolean;
}

const RECONSTRUCTED: ReconstructedDef[] = [
  {
    run_id: "DW-OBS-M3M4-20260823-R1",
    pr_number: 79,
    issue: "70",
    authority_ref: "G2-DW-OBS-M3M4-20260823-R1",
    scope_sha: EVIDENCE.pr["79"].head,
    branch: "auto/SCRUM-555-dw-observation-m3m4-r1",
    ci_run_id: "32589399526",
    milestone: "M3/M4",
    has_alignment_scope: true,
  },
  {
    run_id: "DW-OBS-M0-20260821-R1",
    pr_number: 76,
    issue: "71",
    branch: "auto/SCRUM-555-dw-observation-m0-r2",
    milestone: "M0",
    has_alignment_scope: true,
  },
  {
    run_id: "DW-OBS-M1-20260821-R1",
    pr_number: 77,
    issue: "72",
    branch: "auto/SCRUM-555-dw-observation-m1-r1",
    milestone: "M1",
    has_alignment_scope: true,
  },
  {
    run_id: "DW-OBS-M2-20260822-R1",
    pr_number: 78,
    issue: "73",
    branch: "auto/SCRUM-555-dw-observation-m2-r1",
    milestone: "M2",
    has_alignment_scope: true,
  },
  {
    run_id: "DW-OBS-M3-20260822-R1",
    pr_number: 79,
    issue: "74",
    branch: "auto/SCRUM-555-dw-observation-m3-r1",
    milestone: "M3",
    has_alignment_scope: true,
  },
  {
    run_id: "DW-OBS-M4-20260822-R1",
    pr_number: 79,
    issue: "75",
    branch: "auto/SCRUM-555-dw-observation-m4-r1",
    milestone: "M4",
    has_alignment_scope: false,
  },
];

function buildReconstructed(): {
  runs: RunsRow[];
  sources: SourceRow[];
  artifacts: ArtifactRow[];
} {
  const runs: RunsRow[] = [];
  const sources: SourceRow[] = [];
  const artifacts: ArtifactRow[] = [];

  for (const d of RECONSTRUCTED) {
    const pr = EVIDENCE.pr[String(d.pr_number)];
    const iss = EVIDENCE.issue[d.issue];
    const mergedAt = pr.merged;
    const ci = d.ci_run_id ? EVIDENCE.ci[d.ci_run_id] : undefined;

    runs.push({
      run_id: d.run_id,
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      jira_key: "SCRUM-555",
      parent_issue: d.issue,
      authority_ref: d.authority_ref,
      scope_sha: d.scope_sha,
      base_branch: "pre-prod",
      branch: d.branch,
      pr_number: d.pr_number,
      ci_run_id: d.ci_run_id,
      ci_status: ci ? ci.status : undefined,
      started_at: pr.created,
      completed_at: mergedAt,
      reconstruction_basis: `PR #${d.pr_number} (merged ${mergedAt}) + issue #${d.issue}`,
      source_refs: [`github:pull/${d.pr_number}`, `github:issue/${d.issue}`],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: RECONSTRUCTED_AT,
      payload: { milestone: d.milestone },
    });

    // Normalized run_sources (source_system reflects the REAL system: github)
    sources.push({
      source_id: `pr-${d.run_id}`,
      run_id: d.run_id,
      source_system: "github",
      source_kind: "github_pr",
      capture_provenance_verified: true,
      source_ref: `github:pull/${d.pr_number}`,
      occurred_at: mergedAt,
      evidence_refs: [`PR #${d.pr_number} merged ${mergedAt}`],
    });
    sources.push({
      source_id: `issue-${d.run_id}`,
      run_id: d.run_id,
      source_system: "github",
      source_kind: "github_issue",
      capture_provenance_verified: true,
      source_ref: `github:issue/${d.issue}`,
      occurred_at: iss,
      evidence_refs: [`issue #${d.issue} created ${iss}`],
    });
    if (ci) {
      sources.push({
        source_id: `ci-${d.run_id}`,
        run_id: d.run_id,
        source_system: "github",
        source_kind: "ci_run",
        capture_provenance_verified: true,
        source_ref: `github:actions:run/${d.ci_run_id}`,
        occurred_at: ci.created,
        evidence_refs: [`CI run ${d.ci_run_id} ${ci.status} @ ${ci.head}`],
      });
    }
    sources.push({
      source_id: `recon-${d.run_id}`,
      run_id: d.run_id,
      source_system: "repo_governance",
      source_kind: "reconstruction",
      capture_provenance_verified: false,
      source_ref: ".gwc/tasks/SCRUM-555/history-backfill/RECONSTRUCTION.md",
      occurred_at: RECONSTRUCTED_AT,
      evidence_refs: [`PR #${d.pr_number}`, `issue #${d.issue}`],
    });

    const reconstructedArtifacts: Array<Pick<ArtifactRow, "artifact_type" | "reconstruction_basis" | "source_refs" | "confidence" | "evidence_quality">> = [
      {
        artifact_type: "reconstructed_context_evidence",
        reconstruction_basis: `Reconstructed from issue #${d.issue} context (created ${iss})`,
        source_refs: [`github:issue/${d.issue}`],
        confidence: "HIGH",
        evidence_quality: "STRONG",
      },
      {
        artifact_type: "reconstructed_delivery_record",
        reconstruction_basis: `Reconstructed from PR #${d.pr_number} merge record (merged ${mergedAt})`,
        source_refs: [`github:pull/${d.pr_number}`],
        confidence: "HIGH",
        evidence_quality: "STRONG",
      },
      {
        artifact_type: "reconstructed_ci_evidence",
        reconstruction_basis: ci
          ? `Reconstructed from CI run ${d.ci_run_id} (${ci.status} @ ${ci.head}, ${ci.created})`
          : `No explicit CI run captured; CI provenance inferred from merged PR #${d.pr_number} + issue #${d.issue}`,
        source_refs: ci
          ? [`github:actions:run/${d.ci_run_id}`, `github:pull/${d.pr_number}`]
          : [`github:pull/${d.pr_number}`, `github:issue/${d.issue}`],
        confidence: ci ? "HIGH" : "PARTIAL",
        evidence_quality: ci ? "STRONG" : "PARTIAL",
      },
    ];
    if (d.has_alignment_scope) {
      reconstructedArtifacts.push({
        artifact_type: "reconstructed_alignment_scope",
        reconstruction_basis: `Reconstructed gate alignment scope from PR #${d.pr_number} + issue #${d.issue}`,
        source_refs: [`github:pull/${d.pr_number}`, `github:issue/${d.issue}`],
        confidence: "HIGH",
        evidence_quality: "STRONG",
      });
    }

    for (const a of reconstructedArtifacts) {
      artifacts.push({
        artifact_id: `${d.run_id}:${a.artifact_type}`,
        run_id: d.run_id,
        artifact_type: a.artifact_type,
        artifact_status: "reconstructed",
        original_artifact_present: false,
        source_occurred_at: mergedAt,
        effective_at: mergedAt,
        reconstructed_at: RECONSTRUCTED_AT,
        reconstruction_basis: a.reconstruction_basis,
        source_refs: a.source_refs,
        confidence: a.confidence,
        evidence_quality: a.evidence_quality,
        reconstructed_by: "TaskController/Hermes",
        payload: { milestone: d.milestone },
      });
    }

    if (!d.has_alignment_scope) {
      artifacts.push({
        artifact_id: `${d.run_id}:gate_canonical_artifact`,
        run_id: d.run_id,
        artifact_type: "gate_canonical_artifact",
        artifact_status: "missing_unreconstructable",
        original_artifact_present: false,
        reconstructed_at: RECONSTRUCTED_AT,
        reconstruction_basis: "No persisted canonical gate artifact in evidence; recorded as missing, not invented",
        source_refs: [`github:pull/${d.pr_number}`, `github:issue/${d.issue}`],
        confidence: "UNKNOWN",
        evidence_quality: "NONE",
        reconstructed_by: "TaskController/Hermes",
        payload: { note: "missing_unreconstructable" },
      });
    }
  }

  // M3-M4-EVIDENCE.md is a real persisted historical file → original artifact + repo_governance source
  const evidencePath = ".gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md";
  let digest: string | undefined;
  try {
    const abs = path.resolve(PROJECT_ROOT, "..", "..", evidencePath);
    digest = crypto.createHash("sha256").update(fs.readFileSync(abs)).digest("hex").slice(0, 16);
  } catch {
    digest = undefined;
  }
  sources.push({
    source_id: `evidence-DW-OBS-M3M4-20260823-R1`,
    run_id: "DW-OBS-M3M4-20260823-R1",
    source_system: "repo_governance",
    source_kind: "repo_governance",
    capture_provenance_verified: true,
    source_ref: evidencePath,
    source_digest: digest,
    occurred_at: EVIDENCE.pr["79"].merged,
    evidence_refs: [evidencePath],
  });
  artifacts.push({
    artifact_id: "DW-OBS-M3M4-20260823-R1:M3-M4-EVIDENCE.md",
    run_id: "DW-OBS-M3M4-20260823-R1",
    artifact_type: "historical_evidence_file",
    artifact_status: "original",
    original_artifact_present: true,
    source_occurred_at: EVIDENCE.pr["79"].merged,
    // original artifacts: reconstructed_at = NULL (ingestion created_at carries DB time)
    reconstruction_basis: "Real persisted historical file referenced by evidence",
    source_refs: [evidencePath],
    confidence: "HIGH",
    evidence_quality: "STRONG",
    reconstructed_by: "TaskController/Hermes",
    payload: { repo_ref: evidencePath, digest },
  });

  return { runs, sources, artifacts };
}

// ---- dry-run validation ---------------------------------------------------
interface DryRunReport {
  ok: boolean;
  counts: Record<string, number>;
  byRunKind: Record<string, number>;
  byArtifactStatus: Record<string, number>;
  artifactStatusByRun: Record<string, Record<string, number>>;
  upsertKeyConflicts: string[];
  duplicateRunRows: string[];
  realVsSimSeparation: boolean;
  riChecks: string[];
  provenanceChecks: string[];
  rollback: string;
  errors: string[];
  digest: string;
}

function digestOf(obj: unknown): string {
  return crypto.createHash("sha256").update(JSON.stringify(obj)).digest("hex");
}

function validate(
  runs: RunsRow[],
  events: any[],
  gates: any[],
  nodes: any[],
  sources: SourceRow[],
  artifacts: ArtifactRow[],
): DryRunReport {
  const errors: string[] = [];
  const upsertKeyConflicts: string[] = [];
  const duplicateRunRows: string[] = [];
  const riChecks: string[] = [];
  const provenanceChecks: string[] = [];

  const seen = new Set<string>();
  for (const r of runs) {
    if (seen.has(r.run_id)) duplicateRunRows.push(r.run_id);
    seen.add(r.run_id);
  }

  const evKeys = new Set<string>();
  for (const e of events) {
    const k = `${e.run_id}|${e.source_system}|${e.source_event_id}`;
    if (evKeys.has(k)) upsertKeyConflicts.push(k);
    evKeys.add(k);
  }

  const byRunKind: Record<string, number> = {};
  for (const r of runs) byRunKind[r.run_kind] = (byRunKind[r.run_kind] || 0) + 1;
  const observedReal = byRunKind["observed_real"] || 0;
  const realVsSimSeparation = observedReal === 0;

  const runIds = new Set(runs.map((r) => r.run_id));
  for (const e of events) {
    if (!runIds.has(e.run_id)) riChecks.push(`event ${e.source_event_id} → missing run ${e.run_id}`);
  }
  for (const g of gates) {
    if (!runIds.has(g.run_id)) riChecks.push(`gate ${g.gate_id ?? "?"} → missing run ${g.run_id}`);
  }
  for (const n of nodes) {
    if (!runIds.has(n.run_id)) riChecks.push(`node ${n.node_id ?? "?"} → missing run ${n.run_id}`);
  }
  for (const s of sources) {
    if (!runIds.has(s.run_id)) riChecks.push(`source ${s.source_id} → missing run ${s.run_id}`);
  }
  for (const a of artifacts) {
    if (!runIds.has(a.run_id)) riChecks.push(`artifact ${a.artifact_id} → missing run ${a.run_id}`);
  }

  // Provenance: each reconstructed_history run has >=1 normalized source
  for (const r of runs) {
    if (r.run_kind === "reconstructed_history") {
      if (!sources.some((s) => s.run_id === r.run_id)) {
        provenanceChecks.push(`reconstructed run ${r.run_id} has no run_sources row`);
      }
    }
  }
  // Each artifact's source_refs must resolve to a normalized run_sources.source_ref for the SAME run.
  for (const a of artifacts) {
    const runSources = sources.filter((s) => s.run_id === a.run_id);
    const validRefs = new Set(runSources.map((s) => s.source_ref).filter(Boolean) as string[]);
    for (const ref of a.source_refs) {
      if (!validRefs.has(ref)) {
        provenanceChecks.push(`artifact ${a.artifact_id} ref '${ref}' does not resolve to a run_sources row of run ${a.run_id}`);
      }
    }
    if (a.source_refs.length === 0) {
      provenanceChecks.push(`artifact ${a.artifact_id} has no source_refs`);
    }
  }

  const byArtifactStatus: Record<string, number> = {};
  const artifactStatusByRun: Record<string, Record<string, number>> = {};
  for (const a of artifacts) {
    byArtifactStatus[a.artifact_status] = (byArtifactStatus[a.artifact_status] || 0) + 1;
    artifactStatusByRun[a.run_id] = artifactStatusByRun[a.run_id] || {};
    artifactStatusByRun[a.run_id][a.artifact_status] =
      (artifactStatusByRun[a.run_id][a.artifact_status] || 0) + 1;
  }

  const counts: Record<string, number> = {
    runs: runs.length,
    events: events.length,
    gates: gates.length,
    nodes: nodes.length,
    artifacts: artifacts.length,
    checkpoints: 0,
    edges: 0,
    sources: sources.length,
  };

  const rollback = `DROP TABLE IF EXISTS run_sources, run_edges, run_checkpoints, run_artifacts, run_events, run_nodes, run_gates, runs CASCADE;`;

  if (duplicateRunRows.length) errors.push(`duplicate run rows: ${duplicateRunRows.join(", ")}`);
  if (upsertKeyConflicts.length) errors.push(`event upsert conflicts: ${upsertKeyConflicts.length}`);
  if (riChecks.length) errors.push(`RI violations: ${riChecks.length}`);
  if (!realVsSimSeparation) errors.push(`observed_real=${observedReal} (expected 0)`);
  if (provenanceChecks.length) errors.push(`provenance violations: ${provenanceChecks.length}`);

  const normalized = { runs, events, gates, nodes, sources, artifacts };
  return {
    ok: errors.length === 0,
    counts,
    byRunKind,
    byArtifactStatus,
    artifactStatusByRun,
    upsertKeyConflicts,
    duplicateRunRows,
    realVsSimSeparation,
    riChecks,
    provenanceChecks,
    rollback,
    errors,
    digest: digestOf(normalized),
  };
}

// ---- deterministic DML emission (gated; not executed remotely) -------------
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

function emitDML(
  runs: RunsRow[],
  events: any[],
  gates: any[],
  nodes: any[],
  sources: SourceRow[],
  artifacts: ArtifactRow[],
): string {
  const lines: string[] = [];
  lines.push(`-- DW-OBS-HIST-BACKFILL-R1 · deterministic backfill DML`);
  lines.push(`-- Generated from scripts/backfillHistoricalRuns.ts (deterministic).`);
  lines.push(`-- G6-gated: applied automatically by 'supabase db push --linked --include-all'`);
  lines.push(`-- once committed under supabase/migrations (no separate psql step).`);
  lines.push(`-- Idempotent: ON CONFLICT DO NOTHING (upsert keys).`);
  lines.push(``);
  lines.push(`BEGIN;`);

  for (const r of runs) {
    lines.push(
      `INSERT INTO runs (run_id,run_kind,source_system,epic_id,jira_key,parent_issue,authority_ref,scope_sha,base_branch,branch,pr_number,ci_run_id,ci_status,started_at,completed_at,reconstruction_basis,source_refs,confidence,evidence_quality,reconstructed_by,reconstructed_at,payload) VALUES (` +
        [
          sqlStr(r.run_id), sqlStr(r.run_kind), sqlStr(r.source_system), sqlStr(r.epic_id),
          sqlStr(r.jira_key), sqlStr(r.parent_issue), sqlStr(r.authority_ref), sqlStr(r.scope_sha),
          sqlStr(r.base_branch), sqlStr(r.branch), sqlStr(r.pr_number), sqlStr(r.ci_run_id),
          sqlStr(r.ci_status), sqlStr(r.started_at), sqlStr(r.completed_at), sqlStr(r.reconstruction_basis),
          sqlArr(r.source_refs), sqlStr(r.confidence), sqlStr(r.evidence_quality), sqlStr(r.reconstructed_by),
          sqlStr(r.reconstructed_at), `'{}'::jsonb`,
        ].join(",") +
        `) ON CONFLICT (run_id) DO NOTHING;`,
    );
  }
  for (const e of events) {
    lines.push(
      `INSERT INTO run_events (run_id,source_system,source_event_id,sequence,event_type,decision_kind,occurred_at,gate,node_id,actor,authority_ref,payload_summary,evidence_refs,version,payload) VALUES (` +
        [
          sqlStr(e.run_id), sqlStr(e.source_system), sqlStr(e.source_event_id), sqlStr(e.sequence),
          sqlStr(e.event_type), sqlStr(e.decision_kind), sqlStr(e.occurred_at ?? e.timestamp),
          sqlStr(e.gate), sqlStr(e.node_id), sqlStr(JSON.stringify(e.actor ?? null)), sqlStr(e.authority_ref),
          sqlStr(e.payload_summary), sqlArr(e.evidence_refs ?? []), sqlStr(e.version), `'{}'::jsonb`,
        ].join(",") +
        `) ON CONFLICT (run_id,source_system,source_event_id) DO NOTHING;`,
    );
  }
  for (const g of gates) {
    lines.push(
      `INSERT INTO run_gates (gate_id,run_id,gate_label,boundary,authority_ref,state,summary,node_count,artifact_count,source_refs) VALUES (` +
        [
          sqlStr(g.gate_id), sqlStr(g.run_id), sqlStr(g.gate_label), sqlStr(g.boundary), sqlStr(g.authority_ref),
          sqlStr(g.state), sqlStr(g.summary), sqlStr(g.node_count), sqlStr(g.artifact_count), sqlArr(g.source_refs ?? []),
        ].join(",") +
        `) ON CONFLICT (run_id,gate_id) DO NOTHING;`,
    );
  }
  for (const n of nodes) {
    lines.push(
      `INSERT INTO run_nodes (node_id,run_id,gate_id,family,boundary,state,label,source_refs) VALUES (` +
        [
          sqlStr(n.node_id), sqlStr(n.run_id), sqlStr(n.gate_id), sqlStr(n.family), sqlStr(n.boundary),
          sqlStr(n.state), sqlStr(n.label), sqlArr(n.source_refs ?? []),
        ].join(",") +
        `) ON CONFLICT (run_id,node_id) DO NOTHING;`,
    );
  }
  for (const s of sources) {
    lines.push(
      `INSERT INTO run_sources (source_id,run_id,source_system,source_event_id,source_kind,capture_provenance_verified,source_ref,source_digest,occurred_at,authority_ref,evidence_refs) VALUES (` +
        [
          sqlStr(s.source_id), sqlStr(s.run_id), sqlStr(s.source_system), sqlStr(s.source_event_id),
          sqlStr(s.source_kind), sqlStr(s.capture_provenance_verified), sqlStr(s.source_ref),
          sqlStr(s.source_digest), sqlStr(s.occurred_at), sqlStr(s.authority_ref), sqlArr(s.evidence_refs),
        ].join(",") +
        `) ON CONFLICT (run_id,source_id) DO NOTHING;`,
    );
  }
  for (const a of artifacts) {
    lines.push(
      `INSERT INTO run_artifacts (artifact_id,run_id,artifact_type,artifact_status,original_artifact_present,source_occurred_at,effective_at,reconstructed_at,reconstruction_basis,source_refs,confidence,evidence_quality,reconstructed_by,payload) VALUES (` +
        [
          sqlStr(a.artifact_id), sqlStr(a.run_id), sqlStr(a.artifact_type), sqlStr(a.artifact_status),
          sqlStr(a.original_artifact_present), sqlStr(a.source_occurred_at), sqlStr(a.effective_at),
          sqlStr(a.reconstructed_at), sqlStr(a.reconstruction_basis), sqlArr(a.source_refs),
          sqlStr(a.confidence), sqlStr(a.evidence_quality), sqlStr(a.reconstructed_by), `'{}'::jsonb`,
        ].join(",") +
        `) ON CONFLICT (run_id,artifact_id) DO NOTHING;`,
    );
  }
  lines.push(`COMMIT;`);
  return lines.join("\n");
}

// ---- main ------------------------------------------------------------------
function main() {
  const fix = buildFixtureRuns();
  const rec = buildReconstructed();
  const allRuns = [...fix.runs, ...rec.runs];
  const allSources = [...fix.sources, ...rec.sources];

  const report = validate(allRuns, fix.events, fix.gates, fix.nodes, allSources, rec.artifacts);

  if (process.env.DW_OBS_EMIT_DML) {
    const dml = emitDML(allRuns, fix.events, fix.gates, fix.nodes, allSources, rec.artifacts);
    process.stdout.write(dml);
    process.exit(0);
  }

  const out = {
    migration_ddl: "20260823T080000Z_observatory_history.sql",
    migration_dml: "20260823T090000Z_observatory_backfill_dml.sql",
    target_project: "auswvdxoetufwiaxutib",
    dry_run: true,
    remote_apply: false,
    apply_path: "supabase db push --linked --include-all (committed migration; no separate psql)",
    g6_boundary: "STOP — no remote apply until exact G6 approval bound",
    reconstructed_at: RECONSTRUCTED_AT,
    ...report,
    runs: allRuns,
  };

  console.log(JSON.stringify(out, null, 2));
  process.exit(report.ok ? 0 : 1);
}

main();
