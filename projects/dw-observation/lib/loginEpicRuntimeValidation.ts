import type {
  LoginEpicRuntimeFixture,
  LoginEpicRun,
  GateId,
} from "@/lib/loginEpicRuntimeGraph";
import { GATE_CHAIN } from "@/lib/loginEpicRuntimeGraph";

export interface ValidationIssue {
  level: "error" | "warn";
  message: string;
}

export interface ValidationResult {
  ok: boolean;
  issues: ValidationIssue[];
}

const REQUIRED_GATES: GateId[] = [...GATE_CHAIN];

export function validateLoginEpicFixture(
  fixture: LoginEpicRuntimeFixture,
): ValidationResult {
  const issues: ValidationIssue[] = [];

  if (fixture.epic_id !== "LOGIN-CAPABILITY")
    issues.push({ level: "error", message: `epic_id must be LOGIN-CAPABILITY, got ${fixture.epic_id}` });
  if (fixture.run_count !== 10)
    issues.push({ level: "error", message: `run_count must be 10, got ${fixture.run_count}` });

  const total = fixture.runs.reduce(
    (n, r) => n + r.gates.reduce((m, g) => m + g.nodes.length, 0),
    0,
  );
  if (total !== fixture.runtime_node_count)
    issues.push({
      level: "error",
      message: `runtime_node_count ${fixture.runtime_node_count} != actual total ${total}`,
    });
  if (fixture.runtime_node_count !== 243)
    issues.push({ level: "error", message: `runtime_node_count must be 243, got ${fixture.runtime_node_count}` });

  if (fixture.runs.length !== 10)
    issues.push({ level: "error", message: `runs.length must be 10, got ${fixture.runs.length}` });

  for (const run of fixture.runs as LoginEpicRun[]) {
    const gateIds = run.gates.map((g) => g.id);
    for (const gid of REQUIRED_GATES) {
      if (!gateIds.includes(gid))
        issues.push({ level: "error", message: `${run.id} missing gate ${gid}` });
    }
    // route nodes must exist in their gate
    const allNodeIds = new Set(run.gates.flatMap((g) => g.nodes.map((n) => n.id)));
    for (const step of run.route) {
      if (!allNodeIds.has(step.node_id))
        issues.push({
          level: "error",
          message: `${run.id} route references unknown node ${step.node_id}`,
        });
    }
    // each node must have required non-trivial fields
    for (const g of run.gates) {
      for (const n of g.nodes) {
        if (
          n.fileReads.length === 0 &&
          n.fileWrites.length === 0 &&
          n.artifacts.length === 0
        )
          issues.push({ level: "error", message: `${n.id} has no fileReads/fileWrites/artifacts` });
        if (n.runbook.length === 0)
          issues.push({ level: "error", message: `${n.id} has empty runbook` });
        if (n.taskControllerHistory.length === 0)
          issues.push({ level: "error", message: `${n.id} has empty taskControllerHistory` });
        if (n.checkpoints.length === 0)
          issues.push({ level: "error", message: `${n.id} has empty checkpoints` });
      }
    }
    // G6 boundary rule
    const g6 = run.gates.find((g) => g.id === "G6_PRODUCTION");
    if (g6) {
      for (const n of g6.nodes) {
        const isProdRun = run.run_kind === "observability_deploy_boundary";
        const expect = isProdRun ? "production_boundary" : "not_applicable";
        if (!isProdRun && n.boundary !== "not_applicable" && n.boundary !== "read_only")
          issues.push({
            level: "warn",
            message: `${n.id} (G6, non-production run) boundary=${n.boundary}`,
          });
        void expect;
      }
    }
  }

  return { ok: issues.every((i) => i.level !== "error"), issues };
}
