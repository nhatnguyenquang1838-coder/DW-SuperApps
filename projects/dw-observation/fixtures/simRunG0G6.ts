import type { SimRun } from "@/lib/simRun";

/*
 * M5 (G0-G6 simulated run) — CORRECTED node-architect view fixture.
 * Source-aligned port of dw_run_observatory_correct_node_architect_view.html:
 * 7 gates -> 54 runtime node cards. Node = runtime unit; artifacts / runbook /
 * TaskController history / Executor history / Checkpoints are children of the node.
 * Replay timeline is DERIVED from node.sequence in lib/simRun.ts (no separate
 * timeline object committed -> single source of truth).
 */

export const simRunG0G6 = {
  "run_id": "DW-OBS-ARCH-SIM-G0G6-20260823-R3",
  "task_id": "SCRUM-SIM-G0G6",
  "repository": "nhatnguyenquang1838-coder/DW-SuperApps",
  "base_branch": "pre-prod",
  "base_sha": "a992fa4824db17434f6bdf8aabe8d6f435cc5767",
  "graph_revision": {
    "parent_revision_id": null,
    "revision_id": "scrum-104-20260726",
    "source_sha": "7b7ddbab2dd8ca73d715e6e2ed7c67cda5df8ef1215a27c0e22a9b240722ee9d"
  },
  "status": "simulated_complete",
  "source_basis": {
    "gate_lifecycle": "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
    "g0g1_runbook": "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
    "runtime_node_schema": "schemas/node-architect/runtime-node.schema.json",
    "registry_adapter": "tools/node_architect/viewer/registry_adapter.py",
    "run_history_adapter": "tools/node_architect/viewer/run_history_adapter.py"
  },
  "gates": [
    {
      "id": "G0_CONTEXT",
      "label": "G0 · Context Boot",
      "summary": "Boot from AGENTS.md, resolve project/profile/source, risk and scope.",
      "nodes": [
        {
          "node_id": "intake_context.source-resolution",
          "title": "Source Resolution",
          "description": "Resolves whether the active instruction source is REPO, PACKAGE, or MIXED.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/source-resolution.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/source-resolution.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 1,
          "node_label": "G0_CONTEXT-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/session-inventory.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/source-resolution.json"
          ],
          "reads": [
            "AGENTS.md",
            "workspace.yaml",
            ".dw/powers/gwc/MANIFEST.json",
            ".dw/powers/gwc/AGENTS.md",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json"
          ],
          "runbook": [
            "Read root AGENTS.md",
            "Resolve REPO/PACKAGE/MIXED instruction source",
            "Select validated GWC Power package",
            "Load Node Architect registry and graph"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-001-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "AGENTS.md"
              ]
            },
            {
              "event_id": "tc-001-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/session-inventory.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-001-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/source-resolution.node.json"
              ]
            },
            {
              "event_id": "ex-001-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0/source-resolution.json"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-001",
              "revision": 1,
              "current_node_id": "intake_context.source-resolution",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-75ecfd01",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.request-intake",
          "title": "Request Intake",
          "description": "Normalizes the user request into a bounded intake fact set before any gate decision.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/request-intake.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/request-intake.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 2,
          "node_label": "G0_CONTEXT-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/request-intake.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml"
          ],
          "reads": [
            "user request transcript",
            "active project profile"
          ],
          "runbook": [
            "Parse user objective",
            "Normalize non-goals",
            "Assign task trace",
            "Classify execution mode"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-002-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "user request transcript"
              ]
            },
            {
              "event_id": "tc-002-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0/request-intake.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-002-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/request-intake.node.json"
              ]
            },
            {
              "event_id": "ex-002-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-002",
              "revision": 2,
              "current_node_id": "intake_context.request-intake",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-75cf5b52",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.repo-identity-check",
          "title": "Repository Identity Check",
          "description": "Verifies repository identity, default branch, protected branch, and execution mode assumptions.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/repo-identity-check.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/repo-identity-check.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 3,
          "node_label": "G0_CONTEXT-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/repo-identity.json"
          ],
          "reads": [
            "projects/gwc/project-profile.yaml",
            "target repo AGENTS.md",
            "GitHub repository metadata"
          ],
          "runbook": [
            "Resolve repository owner/name",
            "Verify connector identity",
            "Resolve protected base branch",
            "Record write-enabled/project profile evidence"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-003-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "projects/gwc/project-profile.yaml"
              ]
            },
            {
              "event_id": "tc-003-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-003-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/repo-identity-check.node.json"
              ]
            },
            {
              "event_id": "ex-003-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0/repo-identity.json"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-003",
              "revision": 3,
              "current_node_id": "intake_context.repo-identity-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-761b67cb",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.protected-base-capture",
          "title": "Protected Base Capture",
          "description": "Captures the exact protected base commit SHA used for later gate and PR evidence.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/protected-base-capture.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/protected-base-capture.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 4,
          "node_label": "G0_CONTEXT-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/04-protected-base-capture.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/04-protected-base-capture.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.protected-base-capture",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-004-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-004-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/04-protected-base-capture.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-004-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/protected-base-capture.node.json"
              ]
            },
            {
              "event_id": "ex-004-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/04-protected-base-capture.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-004",
              "revision": 4,
              "current_node_id": "intake_context.protected-base-capture",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-076dde96",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.files-read-scope",
          "title": "Files Read Scope",
          "description": "Renders the required read set for the current task from governance and task-specific inputs.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/files-read-scope.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/files-read-scope.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 5,
          "node_label": "G0_CONTEXT-N05",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/05-files-read-scope.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/05-files-read-scope.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.files-read-scope",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-005-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-005-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/05-files-read-scope.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-005-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/files-read-scope.node.json"
              ]
            },
            {
              "event_id": "ex-005-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/05-files-read-scope.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-005",
              "revision": 5,
              "current_node_id": "intake_context.files-read-scope",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-48aa4c37",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.files-write-scope",
          "title": "Files Write Scope",
          "description": "Renders bounded write paths and exclusions for a later G2 execution envelope.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/files-write-scope.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/files-write-scope.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 6,
          "node_label": "G0_CONTEXT-N06",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/06-files-write-scope.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/06-files-write-scope.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.files-write-scope",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-006-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-006-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/06-files-write-scope.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-006-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/files-write-scope.node.json"
              ]
            },
            {
              "event_id": "ex-006-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/06-files-write-scope.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-006",
              "revision": 6,
              "current_node_id": "intake_context.files-write-scope",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-00e6eaf6",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.risk-classification",
          "title": "Risk Classification",
          "description": "Classifies request risk flags before deciding which gate path is required.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/risk-classification.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/risk-classification.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 7,
          "node_label": "G0_CONTEXT-N07",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/07-risk-classification.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/07-risk-classification.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.risk-classification",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-007-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-007-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/07-risk-classification.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-007-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/risk-classification.node.json"
              ]
            },
            {
              "event_id": "ex-007-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/07-risk-classification.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-007",
              "revision": 7,
              "current_node_id": "intake_context.risk-classification",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-5098d51c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.context-gap-escalation",
          "title": "Context Gap Escalation",
          "description": "Fails closed when required context, repo evidence, or source instruction evidence is missing.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/context-gap-escalation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/context-gap-escalation.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 8,
          "node_label": "G0_CONTEXT-N08",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/08-context-gap-escalation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/08-context-gap-escalation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.context-gap-escalation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-008-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-008-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/08-context-gap-escalation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-008-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/context-gap-escalation.node.json"
              ]
            },
            {
              "event_id": "ex-008-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/08-context-gap-escalation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-008",
              "revision": 8,
              "current_node_id": "intake_context.context-gap-escalation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-42b64b8f",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "intake_context.intake-card-render",
          "title": "Intake Card Render",
          "description": "Produces the standard GWC intake card with request type, reads, writes, risk, gate, and next action.",
          "node_type": "workflow",
          "family": "intake_context",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/intake_context/intake-card-render.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/intake_context/intake-card-render.node.json"
          ],
          "declared_gates": [
            "G0_CONTEXT"
          ],
          "canonical": "canonical",
          "gate_id": "G0_CONTEXT",
          "gate_label": "G0 · Context Boot",
          "sequence": 9,
          "node_label": "G0_CONTEXT-N09",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/09-intake-card-render.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/09-intake-card-render.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
          ],
          "runbook": [
            "Load node descriptor intake_context.intake-card-render",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-009-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-009-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/09-intake-card-render.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-009-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/intake_context/intake-card-render.node.json"
              ]
            },
            {
              "event_id": "ex-009-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/nodes/09-intake-card-render.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-009",
              "revision": 9,
              "current_node_id": "intake_context.intake-card-render",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-630c4859",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g0/context-snapshot.yaml"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G0_CONTEXT-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/"
          ]
        },
        {
          "event_id": "tc-G0_CONTEXT-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g0_context/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G0_CONTEXT-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G0_CONTEXT"
          ]
        }
      ]
    },
    {
      "id": "G1_ALIGNMENT",
      "label": "G1 · Alignment / Decision",
      "summary": "Materialize intake/preflight/options/decision and prepare G2.",
      "nodes": [
        {
          "node_id": "gate_authority.gate-state-resolution",
          "title": "Gate State Resolution",
          "description": "Resolves the active GWC gate from intake facts, task artifacts, and prior gate evidence before any transition is considered.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/gate-state-resolution.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/gate-state-resolution.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 10,
          "node_label": "G1_ALIGNMENT-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/01-gate-state-resolution.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/01-gate-state-resolution.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.gate-state-resolution",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-010-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-010-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/01-gate-state-resolution.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-010-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/gate-state-resolution.node.json"
              ]
            },
            {
              "event_id": "ex-010-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/01-gate-state-resolution.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-010",
              "revision": 10,
              "current_node_id": "gate_authority.gate-state-resolution",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-4b0daaa1",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.evidence-artifact-map",
          "title": "Evidence Artifact Map",
          "description": "Maps required gate evidence to canonical artifact locations so agents do not claim pass without traceable proof.",
          "node_type": "schema",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/evidence-artifact-map.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/evidence-artifact-map.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 11,
          "node_label": "G1_ALIGNMENT-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/evidence-artifact-map.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "reads": [
            "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
            "schemas/gate-action-authority.schema.json"
          ],
          "runbook": [
            "Map each gate to required artifacts",
            "Mark missing artifacts fail-closed",
            "Bind evidence to task/repo/base/scope"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-011-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/GATE_LIFECYCLE_CONTRACT_v1.0.md"
              ]
            },
            {
              "event_id": "tc-011-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1/evidence-artifact-map.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-011-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/evidence-artifact-map.node.json"
              ]
            },
            {
              "event_id": "ex-011-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-011",
              "revision": 11,
              "current_node_id": "gate_authority.evidence-artifact-map",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-7747ffbd",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.scope-hash-calculation",
          "title": "Scope Hash Calculation",
          "description": "Calculates deterministic scope hashes from approved files, actions, exclusions, base SHA, and expiry inputs.",
          "node_type": "tool",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/scope-hash-calculation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/scope-hash-calculation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 12,
          "node_label": "G1_ALIGNMENT-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/scope-hash-input.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/brainstorming/g1-options.yaml"
          ],
          "reads": [
            "g1-intake-brief.yaml",
            "g1-preflight-report.yaml",
            "allowed_paths[]",
            "authorized_actions[]"
          ],
          "runbook": [
            "Normalize allowed paths/actions",
            "Hash canonical scope packet",
            "Bind approval tokens to scope_hash_16"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-012-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "g1-intake-brief.yaml"
              ]
            },
            {
              "event_id": "tc-012-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1/scope-hash-input.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-012-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/scope-hash-calculation.node.json"
              ]
            },
            {
              "event_id": "ex-012-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1/brainstorming/g1-options.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-012",
              "revision": 12,
              "current_node_id": "gate_authority.scope-hash-calculation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-b666e1e4",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.gate-transition-decision",
          "title": "Gate Transition Decision",
          "description": "Determines whether a gate should pass, block, request approval, continue validation, or fail closed.",
          "node_type": "state",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/gate-transition-decision.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/gate-transition-decision.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 13,
          "node_label": "G1_ALIGNMENT-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/04-gate-transition-decision.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/04-gate-transition-decision.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.gate-transition-decision",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-013-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-013-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/04-gate-transition-decision.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-013-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/gate-transition-decision.node.json"
              ]
            },
            {
              "event_id": "ex-013-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/04-gate-transition-decision.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-013",
              "revision": 13,
              "current_node_id": "gate_authority.gate-transition-decision",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-9de8751f",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.approval-token-generation",
          "title": "Approval Token Generation",
          "description": "Produces exact human approval commands with gate, approval request ID, scope hash, and UTC expiry for gated actions.",
          "node_type": "workflow",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/approval-token-generation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/approval-token-generation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 14,
          "node_label": "G1_ALIGNMENT-N05",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/05-approval-token-generation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/05-approval-token-generation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.approval-token-generation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-014-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-014-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/05-approval-token-generation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-014-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/approval-token-generation.node.json"
              ]
            },
            {
              "event_id": "ex-014-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/05-approval-token-generation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-014",
              "revision": 14,
              "current_node_id": "gate_authority.approval-token-generation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-c00269ae",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.g2-execution-envelope-render",
          "title": "G2 Execution Envelope Render",
          "description": "Renders a bounded G2 execution envelope from G1 decision records, Files READ/WRITE, authorized actions, and exclusions.",
          "node_type": "workflow",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 15,
          "node_label": "G1_ALIGNMENT-N06",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/06-g2-execution-envelope-render.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/06-g2-execution-envelope-render.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.g2-execution-envelope-render",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-015-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-015-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/06-g2-execution-envelope-render.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-015-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json"
              ]
            },
            {
              "event_id": "ex-015-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/06-g2-execution-envelope-render.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-015",
              "revision": 15,
              "current_node_id": "gate_authority.g2-execution-envelope-render",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-87158906",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.approval-command-validation",
          "title": "Approval Command Validation",
          "description": "Validates that a human response matches the exact approval command before any G2, G4, G5, or G6 action proceeds.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 16,
          "node_label": "G1_ALIGNMENT-N07",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/07-approval-command-validation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/07-approval-command-validation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.approval-command-validation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-016-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-016-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/07-approval-command-validation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-016-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
              ]
            },
            {
              "event_id": "ex-016-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/07-approval-command-validation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-016",
              "revision": 16,
              "current_node_id": "gate_authority.approval-command-validation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-657e3c97",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.authority-boundary-check",
          "title": "Authority Boundary Check",
          "description": "Blocks actions that cross gate authority boundaries, including merge, deploy, production data, secrets, and branch-history operations.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 17,
          "node_label": "G1_ALIGNMENT-N08",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/08-authority-boundary-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/08-authority-boundary-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.authority-boundary-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-017-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-017-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/08-authority-boundary-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-017-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json"
              ]
            },
            {
              "event_id": "ex-017-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/08-authority-boundary-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-017",
              "revision": 17,
              "current_node_id": "gate_authority.authority-boundary-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-4d3eb0c1",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.blocked-action-escalation",
          "title": "Blocked Action Escalation",
          "description": "Explains blocked actions and generates the next exact approval or remediation command instead of stopping vaguely.",
          "node_type": "workflow",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/blocked-action-escalation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/blocked-action-escalation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G1_ALIGNMENT",
          "gate_label": "G1 · Alignment / Decision",
          "sequence": 18,
          "node_label": "G1_ALIGNMENT-N09",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/09-blocked-action-escalation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/09-blocked-action-escalation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml"
          ],
          "runbook": [
            "Load node descriptor gate_authority.blocked-action-escalation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-018-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-018-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/09-blocked-action-escalation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-018-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/blocked-action-escalation.node.json"
              ]
            },
            {
              "event_id": "ex-018-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/nodes/09-blocked-action-escalation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-018",
              "revision": 18,
              "current_node_id": "gate_authority.blocked-action-escalation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-d0065b85",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g1/intake/g1-intake-brief.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g1/preflight/g1-preflight-report.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g1/brainstorming/g1-options.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g1/decision/g1-decision-record.yaml"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G1_ALIGNMENT-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/"
          ]
        },
        {
          "event_id": "tc-G1_ALIGNMENT-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g1_alignment/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G1_ALIGNMENT-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G1_ALIGNMENT"
          ]
        }
      ]
    },
    {
      "id": "G2_EXECUTION",
      "label": "G2 · Execution Runtime",
      "summary": "Validated approval, checkpoint engine, branch/write/export/projection.",
      "nodes": [
        {
          "node_id": "gate_authority.g2-execution-envelope-render",
          "title": "G2 Execution Envelope Render",
          "description": "Renders a bounded G2 execution envelope from G1 decision records, Files READ/WRITE, authorized actions, and exclusions.",
          "node_type": "workflow",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 19,
          "node_label": "G2_EXECUTION-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/01-g2-execution-envelope-render.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/01-g2-execution-envelope-render.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor gate_authority.g2-execution-envelope-render",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-019-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-019-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/01-g2-execution-envelope-render.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-019-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/g2-execution-envelope-render.node.json"
              ]
            },
            {
              "event_id": "ex-019-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/01-g2-execution-envelope-render.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-019",
              "revision": 19,
              "current_node_id": "gate_authority.g2-execution-envelope-render",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-87158906",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.approval-command-validation",
          "title": "Approval Command Validation",
          "description": "Validates that a human response matches the exact approval command before any G2, G4, G5, or G6 action proceeds.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 20,
          "node_label": "G2_EXECUTION-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/02-approval-command-validation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/02-approval-command-validation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor gate_authority.approval-command-validation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-020-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-020-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/02-approval-command-validation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-020-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
              ]
            },
            {
              "event_id": "ex-020-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/02-approval-command-validation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-020",
              "revision": 20,
              "current_node_id": "gate_authority.approval-command-validation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-657e3c97",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "runtime_checkpoint.lease-acquisition",
          "title": "Lease Acquisition",
          "description": "Acquire bounded work leases before mutating guarded branch state.",
          "node_type": "connector",
          "family": "runtime_checkpoint",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/runtime_checkpoint/lease-acquisition.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/runtime_checkpoint/lease-acquisition.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 21,
          "node_label": "G2_EXECUTION-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/runtime-lease.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/checkpoint-000.json"
          ],
          "reads": [
            "g2/execution-envelope.yaml",
            "checkpoint store"
          ],
          "runbook": [
            "Load checkpoint",
            "Acquire lease",
            "Set fencing token",
            "Mark active executor"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-021-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "g2/execution-envelope.yaml"
              ]
            },
            {
              "event_id": "tc-021-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2/runtime-lease.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-021-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/runtime_checkpoint/lease-acquisition.node.json"
              ]
            },
            {
              "event_id": "ex-021-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2/checkpoint-000.json"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-021",
              "revision": 21,
              "current_node_id": "runtime_checkpoint.lease-acquisition",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-d804309c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "runtime_checkpoint.checkpoint-capture",
          "title": "Checkpoint Capture",
          "description": "Capture a deterministic checkpoint before bounded execution state changes.",
          "node_type": "state",
          "family": "runtime_checkpoint",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-capture.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-capture.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 22,
          "node_label": "G2_EXECUTION-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/04-checkpoint-capture.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/04-checkpoint-capture.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor runtime_checkpoint.checkpoint-capture",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-022-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-022-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/04-checkpoint-capture.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-022-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-capture.node.json"
              ]
            },
            {
              "event_id": "ex-022-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/04-checkpoint-capture.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-022",
              "revision": 22,
              "current_node_id": "runtime_checkpoint.checkpoint-capture",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-ecef0708",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "runtime_checkpoint.cas-write-guard",
          "title": "Cas Write Guard",
          "description": "Guard branch and artifact writes with compare-and-swap expectations.",
          "node_type": "gate",
          "family": "runtime_checkpoint",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/runtime_checkpoint/cas-write-guard.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/runtime_checkpoint/cas-write-guard.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 23,
          "node_label": "G2_EXECUTION-N05",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/05-cas-write-guard.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/05-cas-write-guard.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor runtime_checkpoint.cas-write-guard",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-023-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-023-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/05-cas-write-guard.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-023-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/runtime_checkpoint/cas-write-guard.node.json"
              ]
            },
            {
              "event_id": "ex-023-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/05-cas-write-guard.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-023",
              "revision": 23,
              "current_node_id": "runtime_checkpoint.cas-write-guard",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-c8a4f4e5",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.branch-creation",
          "title": "Branch Creation",
          "description": "Create guarded branches from exact approved base SHA.",
          "node_type": "connector",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/branch-creation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/branch-creation.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 24,
          "node_label": "G2_EXECUTION-N06",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/06-branch-creation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/06-branch-creation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor repo_delivery.branch-creation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-024-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-024-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/06-branch-creation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-024-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/branch-creation.node.json"
              ]
            },
            {
              "event_id": "ex-024-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/06-branch-creation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-024",
              "revision": 24,
              "current_node_id": "repo_delivery.branch-creation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-3474fe5c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.scoped-file-write",
          "title": "Scoped File Write",
          "description": "Write only files allowed by the active G2 execution envelope.",
          "node_type": "tool",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/scoped-file-write.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/scoped-file-write.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 25,
          "node_label": "G2_EXECUTION-N07",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/write-readback.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/changed-files.json"
          ],
          "reads": [
            "approved design contract",
            "allowed_paths[]",
            "repo files"
          ],
          "runbook": [
            "Read target files",
            "Apply bounded patch",
            "Read back changed bytes",
            "Reject scope drift"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-025-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "approved design contract"
              ]
            },
            {
              "event_id": "tc-025-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2/write-readback.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-025-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/scoped-file-write.node.json"
              ]
            },
            {
              "event_id": "ex-025-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2/changed-files.json"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-025",
              "revision": 25,
              "current_node_id": "repo_delivery.scoped-file-write",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-d9f4746b",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "runtime_checkpoint.checkpoint-persist",
          "title": "Checkpoint Persist",
          "description": "Persist checkpoint artifacts to the approved workspace without production data access.",
          "node_type": "tool",
          "family": "runtime_checkpoint",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-persist.node.json",
          "source_status": "canonical_explicit",
          "maturity": "candidate",
          "implementation_refs": [
            "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-persist.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 26,
          "node_label": "G2_EXECUTION-N08",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/08-checkpoint-persist.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/08-checkpoint-persist.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor runtime_checkpoint.checkpoint-persist",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-026-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-026-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/08-checkpoint-persist.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-026-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/runtime_checkpoint/checkpoint-persist.node.json"
              ]
            },
            {
              "event_id": "ex-026-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/08-checkpoint-persist.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-026",
              "revision": 26,
              "current_node_id": "runtime_checkpoint.checkpoint-persist",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-afb9c83c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "package-export-package-manifest-load",
          "title": "Package Manifest Load",
          "description": "Load the approved project package manifest and preserve its stable entry order before export.",
          "node_type": "tool",
          "family": "package_export",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/package_export/package-manifest-load.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/package_export/package-manifest-load.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 27,
          "node_label": "G2_EXECUTION-N09",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/09-package-export-package-manifest-load.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/09-package-export-package-manifest-load.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor package-export-package-manifest-load",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-027-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-027-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/09-package-export-package-manifest-load.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-027-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/package_export/package-manifest-load.node.json"
              ]
            },
            {
              "event_id": "ex-027-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/09-package-export-package-manifest-load.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-027",
              "revision": 27,
              "current_node_id": "package-export-package-manifest-load",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-d93593a0",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "package-export-governance-tree-build",
          "title": "Governance Tree Build",
          "description": "Copy approved source bytes into the generated governance tree without changing canonical authority.",
          "node_type": "workflow",
          "family": "package_export",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/package_export/governance-tree-build.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/package_export/governance-tree-build.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 28,
          "node_label": "G2_EXECUTION-N10",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/10-package-export-governance-tree-build.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/10-package-export-governance-tree-build.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor package-export-governance-tree-build",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-028-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-028-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/10-package-export-governance-tree-build.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-028-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/package_export/governance-tree-build.node.json"
              ]
            },
            {
              "event_id": "ex-028-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/10-package-export-governance-tree-build.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-028",
              "revision": 28,
              "current_node_id": "package-export-governance-tree-build",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-7f84fa17",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "package-export-export-manifest-generation",
          "title": "Export Manifest Generation",
          "description": "Generate deterministic export evidence with source identity, entry status, byte counts, and SHA-256 values.",
          "node_type": "workflow",
          "family": "package_export",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/package_export/export-manifest-generation.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/package_export/export-manifest-generation.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 29,
          "node_label": "G2_EXECUTION-N11",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/11-package-export-export-manifest-generation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/11-package-export-export-manifest-generation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor package-export-export-manifest-generation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-029-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-029-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/11-package-export-export-manifest-generation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-029-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/package_export/export-manifest-generation.node.json"
              ]
            },
            {
              "event_id": "ex-029-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/11-package-export-export-manifest-generation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-029",
              "revision": 29,
              "current_node_id": "package-export-export-manifest-generation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-3cf8f256",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "package-export-deterministic-hash-verification",
          "title": "Deterministic Hash Verification",
          "description": "Read back generated files and verify source, target, and manifest hashes for the approved inputs.",
          "node_type": "gate",
          "family": "package_export",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/package_export/deterministic-hash-verification.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/package_export/deterministic-hash-verification.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 30,
          "node_label": "G2_EXECUTION-N12",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/12-package-export-deterministic-hash-verification.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/12-package-export-deterministic-hash-verification.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor package-export-deterministic-hash-verification",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-030-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-030-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/12-package-export-deterministic-hash-verification.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-030-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/package_export/deterministic-hash-verification.node.json"
              ]
            },
            {
              "event_id": "ex-030-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/12-package-export-deterministic-hash-verification.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-030",
              "revision": 30,
              "current_node_id": "package-export-deterministic-hash-verification",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-56d73122",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "sync-projection-task-center-sync",
          "title": "Task Center Sync",
          "description": "Synchronize bounded task metadata to Task Center while preserving repository and gate evidence as canonical.",
          "node_type": "connector",
          "family": "sync_projection",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/sync_projection/task-center-sync.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/sync_projection/task-center-sync.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "audit_projection",
          "gate_id": "G2_EXECUTION",
          "gate_label": "G2 · Execution Runtime",
          "sequence": 31,
          "node_label": "G2_EXECUTION-N13",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/13-sync-projection-task-center-sync.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/13-sync-projection-task-center-sync.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json"
          ],
          "runbook": [
            "Load node descriptor sync-projection-task-center-sync",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-031-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-031-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/13-sync-projection-task-center-sync.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-031-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/sync_projection/task-center-sync.node.json"
              ]
            },
            {
              "event_id": "ex-031-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/nodes/13-sync-projection-task-center-sync.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-031",
              "revision": 31,
              "current_node_id": "sync-projection-task-center-sync",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-69002afd",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g2/execution-envelope.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g2/action-authority.json",
        ".gwc/tasks/SCRUM-SIM-G0G6/g2/runtime-checkpoint.json"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G2_EXECUTION-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/"
          ]
        },
        {
          "event_id": "tc-G2_EXECUTION-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g2_execution/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G2_EXECUTION-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G2_EXECUTION"
          ]
        }
      ]
    },
    {
      "id": "G3_PR",
      "label": "G3 · PR / Review",
      "summary": "Diff, validation, CI, Draft PR and G3 pass decision.",
      "nodes": [
        {
          "node_id": "repo_delivery.diff-readback",
          "title": "Diff Readback",
          "description": "Read back compare metadata and changed-file scope after writes.",
          "node_type": "workflow",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/diff-readback.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/diff-readback.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 32,
          "node_label": "G3_PR-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/01-diff-readback.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/01-diff-readback.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor repo_delivery.diff-readback",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-032-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-032-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/01-diff-readback.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-032-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/diff-readback.node.json"
              ]
            },
            {
              "event_id": "ex-032-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/01-diff-readback.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-032",
              "revision": 32,
              "current_node_id": "repo_delivery.diff-readback",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-00780ab9",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-unit-test-mapping",
          "title": "Unit Test Mapping",
          "description": "Map changed runtime catalog artifacts to focused unit tests.",
          "node_type": "workflow",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/unit-test-mapping.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/unit-test-mapping.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 33,
          "node_label": "G3_PR-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/02-validation-quality-unit-test-mapping.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/02-validation-quality-unit-test-mapping.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor validation-quality-unit-test-mapping",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-033-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-033-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/02-validation-quality-unit-test-mapping.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-033-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/unit-test-mapping.node.json"
              ]
            },
            {
              "event_id": "ex-033-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/02-validation-quality-unit-test-mapping.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-033",
              "revision": 33,
              "current_node_id": "validation-quality-unit-test-mapping",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-24f98f98",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-schema-validation",
          "title": "Schema Validation",
          "description": "Validate runtime node payloads against the canonical runtime-node schema.",
          "node_type": "tool",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/schema-validation.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/schema-validation.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 34,
          "node_label": "G3_PR-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/03-validation-quality-schema-validation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/03-validation-quality-schema-validation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor validation-quality-schema-validation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-034-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-034-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/03-validation-quality-schema-validation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-034-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/schema-validation.node.json"
              ]
            },
            {
              "event_id": "ex-034-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/03-validation-quality-schema-validation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-034",
              "revision": 34,
              "current_node_id": "validation-quality-schema-validation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-9cd1760e",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-validator-execution",
          "title": "Validator Execution",
          "description": "Run stdlib validators and capture deterministic return codes.",
          "node_type": "tool",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/validator-execution.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/validator-execution.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 35,
          "node_label": "G3_PR-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/04-validation-quality-validator-execution.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/04-validation-quality-validator-execution.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor validation-quality-validator-execution",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-035-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-035-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/04-validation-quality-validator-execution.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-035-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/validator-execution.node.json"
              ]
            },
            {
              "event_id": "ex-035-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/04-validation-quality-validator-execution.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-035",
              "revision": 35,
              "current_node_id": "validation-quality-validator-execution",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-9b6e03a1",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.ci-run-capture",
          "title": "Ci Run Capture",
          "description": "Capture exact-head CI workflow status for G3 evidence.",
          "node_type": "tool",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/ci-run-capture.node.json",
          "source_status": "canonical_explicit",
          "maturity": "candidate",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/ci-run-capture.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 36,
          "node_label": "G3_PR-N05",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/05-ci-run-capture.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/05-ci-run-capture.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor repo_delivery.ci-run-capture",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-036-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-036-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/05-ci-run-capture.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-036-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/ci-run-capture.node.json"
              ]
            },
            {
              "event_id": "ex-036-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/05-ci-run-capture.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-036",
              "revision": 36,
              "current_node_id": "repo_delivery.ci-run-capture",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-1d56997c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-ci-evidence-capture",
          "title": "CI Evidence Capture",
          "description": "Capture exact-head workflow runs and status evidence for G3.",
          "node_type": "workflow",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/ci-evidence-capture.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/ci-evidence-capture.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 37,
          "node_label": "G3_PR-N06",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/workflow-jobs.json"
          ],
          "reads": [
            "GitHub Actions runs",
            "exact head SHA",
            "required checks"
          ],
          "runbook": [
            "Read exact-head workflow run",
            "Read job steps",
            "Capture logs/artifacts",
            "Reject stale SHA evidence"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-037-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "GitHub Actions runs"
              ]
            },
            {
              "event_id": "tc-037-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-037-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/ci-evidence-capture.node.json"
              ]
            },
            {
              "event_id": "ex-037-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3/workflow-jobs.json"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-037",
              "revision": 37,
              "current_node_id": "validation-quality-ci-evidence-capture",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-e56d94b5",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-evidence-quality-check",
          "title": "Evidence Quality Check",
          "description": "Check evidence completeness before declaring G3 PASS.",
          "node_type": "gate",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/evidence-quality-check.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/evidence-quality-check.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 38,
          "node_label": "G3_PR-N07",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/07-validation-quality-evidence-quality-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/07-validation-quality-evidence-quality-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor validation-quality-evidence-quality-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-038-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-038-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/07-validation-quality-evidence-quality-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-038-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/evidence-quality-check.node.json"
              ]
            },
            {
              "event_id": "ex-038-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/07-validation-quality-evidence-quality-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-038",
              "revision": 38,
              "current_node_id": "validation-quality-evidence-quality-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-9f2c5ce9",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.draft-pr-creation",
          "title": "Draft Pr Creation",
          "description": "Open Draft PRs with approved scope, base, head, and exclusions.",
          "node_type": "connector",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/draft-pr-creation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/draft-pr-creation.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "canonical",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 39,
          "node_label": "G3_PR-N08",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/pr-readback.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml"
          ],
          "reads": [
            "branch head SHA",
            "diff-readback.json",
            "validator-output.json"
          ],
          "runbook": [
            "Create/update Draft PR",
            "Bind base/head/branch",
            "Record PR readback",
            "Stop before G4 merge"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-039-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "branch head SHA"
              ]
            },
            {
              "event_id": "tc-039-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3/pr-readback.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-039-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/draft-pr-creation.node.json"
              ]
            },
            {
              "event_id": "ex-039-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-039",
              "revision": 39,
              "current_node_id": "repo_delivery.draft-pr-creation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-8179b7b9",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.pr-blocker-check",
          "title": "Pr Blocker Check",
          "description": "Check mergeability, review threads, review submissions, and unresolved blockers.",
          "node_type": "gate",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/pr-blocker-check.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/pr-blocker-check.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "canonical",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 40,
          "node_label": "G3_PR-N09",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/09-pr-blocker-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/09-pr-blocker-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor repo_delivery.pr-blocker-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-040-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-040-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/09-pr-blocker-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-040-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/pr-blocker-check.node.json"
              ]
            },
            {
              "event_id": "ex-040-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/09-pr-blocker-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-040",
              "revision": 40,
              "current_node_id": "repo_delivery.pr-blocker-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-2ed3c77d",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "validation-quality-g3-pass-decision",
          "title": "G3 Pass Decision",
          "description": "Decide whether exact-head CI, tests, and blocker checks satisfy G3.",
          "node_type": "gate",
          "family": "validation_quality",
          "authority_boundary": "g3_required",
          "catalog_path": "core/node-architect/node-catalog/validation_quality/g3-pass-decision.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/validation_quality/g3-pass-decision.node.json"
          ],
          "declared_gates": [
            "G3_PR"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G3_PR",
          "gate_label": "G3 · PR / Review",
          "sequence": 41,
          "node_label": "G3_PR-N10",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/10-validation-quality-g3-pass-decision.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/10-validation-quality-g3-pass-decision.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json"
          ],
          "runbook": [
            "Load node descriptor validation-quality-g3-pass-decision",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-041-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-041-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/10-validation-quality-g3-pass-decision.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-041-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/validation_quality/g3-pass-decision.node.json"
              ]
            },
            {
              "event_id": "ex-041-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/nodes/10-validation-quality-g3-pass-decision.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-041",
              "revision": 41,
              "current_node_id": "validation-quality-g3-pass-decision",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-510f117c",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g3/delivery-record.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g3/ci-evidence.json",
        ".gwc/tasks/SCRUM-SIM-G0G6/g3/pr-readback.json"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G3_PR-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/"
          ]
        },
        {
          "event_id": "tc-G3_PR-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g3_pr/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G3_PR-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G3_PR"
          ]
        }
      ]
    },
    {
      "id": "G4_MERGE",
      "label": "G4 · Merge Authority",
      "summary": "Separate merge approval, exact head merge, audit projection.",
      "nodes": [
        {
          "node_id": "gate_authority.authority-boundary-check",
          "title": "Authority Boundary Check",
          "description": "Blocks actions that cross gate authority boundaries, including merge, deploy, production data, secrets, and branch-history operations.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G4_MERGE",
          "gate_label": "G4 · Merge Authority",
          "sequence": 42,
          "node_label": "G4_MERGE-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/01-authority-boundary-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/01-authority-boundary-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-readback.json"
          ],
          "runbook": [
            "Load node descriptor gate_authority.authority-boundary-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-042-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-042-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/01-authority-boundary-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-042-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/authority-boundary-check.node.json"
              ]
            },
            {
              "event_id": "ex-042-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/01-authority-boundary-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-042",
              "revision": 42,
              "current_node_id": "gate_authority.authority-boundary-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-4d3eb0c1",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "gate_authority.approval-command-validation",
          "title": "Approval Command Validation",
          "description": "Validates that a human response matches the exact approval command before any G2, G4, G5, or G6 action proceeds.",
          "node_type": "gate",
          "family": "gate_authority",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
          ],
          "declared_gates": [
            "G1_ALIGNMENT",
            "G2_EXECUTION"
          ],
          "canonical": "canonical",
          "gate_id": "G4_MERGE",
          "gate_label": "G4 · Merge Authority",
          "sequence": 43,
          "node_label": "G4_MERGE-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/02-approval-command-validation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/02-approval-command-validation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-readback.json"
          ],
          "runbook": [
            "Load node descriptor gate_authority.approval-command-validation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-043-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-043-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/02-approval-command-validation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-043-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/gate_authority/approval-command-validation.node.json"
              ]
            },
            {
              "event_id": "ex-043-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/02-approval-command-validation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-043",
              "revision": 43,
              "current_node_id": "gate_authority.approval-command-validation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-657e3c97",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "lifecycle.g4-merge-approval",
          "title": "lifecycle.g4-merge-approval",
          "description": "Lifecycle node for lifecycle.g4-merge-approval.",
          "node_type": "runtime-node",
          "family": "lifecycle_contract",
          "authority_boundary": "gate_required",
          "catalog_path": "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [],
          "declared_gates": [
            "G4_MERGE"
          ],
          "canonical": "lifecycle",
          "gate_id": "G4_MERGE",
          "gate_label": "G4 · Merge Authority",
          "sequence": 44,
          "node_label": "G4_MERGE-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml"
          ],
          "reads": [
            "g3/delivery-record.yaml",
            "PR readback",
            "CI evidence",
            "human APPROVE G4 line"
          ],
          "runbook": [
            "Generate G4 approval envelope",
            "Validate exact PR/head/base/method",
            "Require human command",
            "Fail stale approval"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-044-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "g3/delivery-record.yaml"
              ]
            },
            {
              "event_id": "tc-044-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-044-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/GATE_LIFECYCLE_CONTRACT_v1.0.md"
              ]
            },
            {
              "event_id": "ex-044-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-044",
              "revision": 44,
              "current_node_id": "lifecycle.g4-merge-approval",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-2820199a",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "repo_delivery.ready-for-review-promotion",
          "title": "Ready For Review Promotion",
          "description": "Promote Draft PR to Ready for Review only after G3 criteria pass.",
          "node_type": "connector",
          "family": "repo_delivery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/repo_delivery/ready-for-review-promotion.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/repo_delivery/ready-for-review-promotion.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "canonical",
          "gate_id": "G4_MERGE",
          "gate_label": "G4 · Merge Authority",
          "sequence": 45,
          "node_label": "G4_MERGE-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/04-ready-for-review-promotion.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/04-ready-for-review-promotion.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-readback.json"
          ],
          "runbook": [
            "Load node descriptor repo_delivery.ready-for-review-promotion",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-045-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-045-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/04-ready-for-review-promotion.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-045-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/repo_delivery/ready-for-review-promotion.node.json"
              ]
            },
            {
              "event_id": "ex-045-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/04-ready-for-review-promotion.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-045",
              "revision": 45,
              "current_node_id": "repo_delivery.ready-for-review-promotion",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-2c19eef9",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "sync-projection-external-audit-event-projection",
          "title": "External Audit Event Projection",
          "description": "Project sanitized lifecycle events to external audit surfaces without copying secrets or approval commands.",
          "node_type": "projection",
          "family": "sync_projection",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "audit_projection",
          "gate_id": "G4_MERGE",
          "gate_label": "G4 · Merge Authority",
          "sequence": 46,
          "node_label": "G4_MERGE-N05",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/05-sync-projection-external-audit-event-projection.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/05-sync-projection-external-audit-event-projection.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-readback.json"
          ],
          "runbook": [
            "Load node descriptor sync-projection-external-audit-event-projection",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-046-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-046-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/05-sync-projection-external-audit-event-projection.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-046-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json"
              ]
            },
            {
              "event_id": "ex-046-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/nodes/05-sync-projection-external-audit-event-projection.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-046",
              "revision": 46,
              "current_node_id": "sync-projection-external-audit-event-projection",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-f743a398",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-approval.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g4/merge-readback.json"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G4_MERGE-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/"
          ]
        },
        {
          "event_id": "tc-G4_MERGE-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g4_merge/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G4_MERGE-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G4_MERGE"
          ]
        }
      ]
    },
    {
      "id": "G5_DEPLOY",
      "label": "G5 · Deploy / Status",
      "summary": "Read-only status/deploy observability and drift handling.",
      "nodes": [
        {
          "node_id": "scale_control.exact-head-readiness-check",
          "title": "Exact Head Readiness Check",
          "description": "Require validation, workflow, and artifact evidence to bind to the exact current branch or merge commit before readiness can pass.",
          "node_type": "gate",
          "family": "scale_control",
          "authority_boundary": "g5_required",
          "catalog_path": "core/node-architect/node-catalog/scale_control/exact-head-readiness-check.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/scale_control/exact-head-readiness-check.node.json"
          ],
          "declared_gates": [
            "G5_DEPLOY"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G5_DEPLOY",
          "gate_label": "G5 · Deploy / Status",
          "sequence": 47,
          "node_label": "G5_DEPLOY-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/01-exact-head-readiness-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/01-exact-head-readiness-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/deployment-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/status-verify.json"
          ],
          "runbook": [
            "Load node descriptor scale_control.exact-head-readiness-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-047-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-047-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/01-exact-head-readiness-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-047-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/scale_control/exact-head-readiness-check.node.json"
              ]
            },
            {
              "event_id": "ex-047-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/01-exact-head-readiness-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-047",
              "revision": 47,
              "current_node_id": "scale_control.exact-head-readiness-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-706b8f3a",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "scale_control.workflow-run-observability",
          "title": "Workflow Run Observability",
          "description": "Project exact-head CI evidence across pull-request and post-merge push events while distinguishing missing runs from connector visibility gaps.",
          "node_type": "projection",
          "family": "scale_control",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/scale_control/workflow-run-observability.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/scale_control/workflow-run-observability.node.json"
          ],
          "declared_gates": [
            "G5_DEPLOY"
          ],
          "canonical": "audit_projection",
          "gate_id": "G5_DEPLOY",
          "gate_label": "G5 · Deploy / Status",
          "sequence": 48,
          "node_label": "G5_DEPLOY-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/02-workflow-run-observability.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/02-workflow-run-observability.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/deployment-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/status-verify.json"
          ],
          "runbook": [
            "Load node descriptor scale_control.workflow-run-observability",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-048-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-048-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/02-workflow-run-observability.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-048-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/scale_control/workflow-run-observability.node.json"
              ]
            },
            {
              "event_id": "ex-048-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/02-workflow-run-observability.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-048",
              "revision": 48,
              "current_node_id": "scale_control.workflow-run-observability",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-cb589fc0",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "scale_control.previous-batch-g5-verification",
          "title": "Previous Batch G5 Verification",
          "description": "Bind the next batch admission decision to successful post-merge validation evidence for the exact previous merge commit.",
          "node_type": "workflow",
          "family": "scale_control",
          "authority_boundary": "g5_required",
          "catalog_path": "core/node-architect/node-catalog/scale_control/previous-batch-g5-verification.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/scale_control/previous-batch-g5-verification.node.json"
          ],
          "declared_gates": [
            "G5_DEPLOY"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G5_DEPLOY",
          "gate_label": "G5 · Deploy / Status",
          "sequence": 49,
          "node_label": "G5_DEPLOY-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/03-previous-batch-g5-verification.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/03-previous-batch-g5-verification.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/deployment-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/status-verify.json"
          ],
          "runbook": [
            "Load node descriptor scale_control.previous-batch-g5-verification",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-049-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-049-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/03-previous-batch-g5-verification.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-049-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/scale_control/previous-batch-g5-verification.node.json"
              ]
            },
            {
              "event_id": "ex-049-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/03-previous-batch-g5-verification.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-049",
              "revision": 49,
              "current_node_id": "scale_control.previous-batch-g5-verification",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-a235cf7f",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "failure_recovery.version-drift-rollback-routing",
          "title": "Version Drift Rollback Routing",
          "description": "Pin or restart on node-version drift and route rollback evidence without granting deployment authority.",
          "node_type": "workflow",
          "family": "failure_recovery",
          "authority_boundary": "g5_required",
          "catalog_path": "core/node-architect/node-catalog/failure_recovery/version-drift-rollback-routing.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/failure_recovery/version-drift-rollback-routing.node.json"
          ],
          "declared_gates": [
            "G5_DEPLOY"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G5_DEPLOY",
          "gate_label": "G5 · Deploy / Status",
          "sequence": 50,
          "node_label": "G5_DEPLOY-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/04-version-drift-rollback-routing.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/04-version-drift-rollback-routing.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/deployment-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g5/status-verify.json"
          ],
          "runbook": [
            "Load node descriptor failure_recovery.version-drift-rollback-routing",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-050-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-050-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/04-version-drift-rollback-routing.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-050-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/failure_recovery/version-drift-rollback-routing.node.json"
              ]
            },
            {
              "event_id": "ex-050-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/nodes/04-version-drift-rollback-routing.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-050",
              "revision": 50,
              "current_node_id": "failure_recovery.version-drift-rollback-routing",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-3474d7f0",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g5/deployment-approval.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g5/status-verify.json"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G5_DEPLOY-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/"
          ]
        },
        {
          "event_id": "tc-G5_DEPLOY-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g5_deploy/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G5_DEPLOY-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G5_DEPLOY"
          ]
        }
      ]
    },
    {
      "id": "G6_PRODUCTION_DATA",
      "label": "G6 · Production Data",
      "summary": "Production approval, boundary check, audit/readback/reconciliation.",
      "nodes": [
        {
          "node_id": "lifecycle.g6-production-approval",
          "title": "lifecycle.g6-production-approval",
          "description": "Lifecycle node for lifecycle.g6-production-approval.",
          "node_type": "runtime-node",
          "family": "lifecycle_contract",
          "authority_boundary": "gate_required",
          "catalog_path": "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [],
          "declared_gates": [
            "G6_PRODUCTION_DATA"
          ],
          "canonical": "lifecycle",
          "gate_id": "G6_PRODUCTION_DATA",
          "gate_label": "G6 · Production Data",
          "sequence": 51,
          "node_label": "G6_PRODUCTION_DATA-N01",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml"
          ],
          "reads": [
            "production change plan",
            "rollback plan",
            "privacy boundary",
            "human APPROVE G6 line"
          ],
          "runbook": [
            "Generate production approval envelope",
            "Bind target/data/config scope",
            "Require rollback plan",
            "Require human command"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-051-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "production change plan"
              ]
            },
            {
              "event_id": "tc-051-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-051-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/GATE_LIFECYCLE_CONTRACT_v1.0.md"
              ]
            },
            {
              "event_id": "ex-051-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-051",
              "revision": 51,
              "current_node_id": "lifecycle.g6-production-approval",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-fed6ece4",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "sync-projection-projection-privacy-boundary-check",
          "title": "Projection Privacy Boundary Check",
          "description": "Block secrets, credentials, production data, hidden reasoning, and unrestricted payloads from external projection.",
          "node_type": "gate",
          "family": "sync_projection",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/sync_projection/projection-privacy-boundary-check.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/sync_projection/projection-privacy-boundary-check.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "audit_projection",
          "gate_id": "G6_PRODUCTION_DATA",
          "gate_label": "G6 · Production Data",
          "sequence": 52,
          "node_label": "G6_PRODUCTION_DATA-N02",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/02-sync-projection-projection-privacy-boundary-check.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/02-sync-projection-projection-privacy-boundary-check.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-readback.json"
          ],
          "runbook": [
            "Load node descriptor sync-projection-projection-privacy-boundary-check",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-052-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-052-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/02-sync-projection-projection-privacy-boundary-check.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-052-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/sync_projection/projection-privacy-boundary-check.node.json"
              ]
            },
            {
              "event_id": "ex-052-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/02-sync-projection-projection-privacy-boundary-check.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-052",
              "revision": 52,
              "current_node_id": "sync-projection-projection-privacy-boundary-check",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-42dd13f5",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "sync-projection-external-audit-event-projection",
          "title": "External Audit Event Projection",
          "description": "Project sanitized lifecycle events to external audit surfaces without copying secrets or approval commands.",
          "node_type": "projection",
          "family": "sync_projection",
          "authority_boundary": "read_only",
          "catalog_path": "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json",
          "source_status": "lifecycle_artifact",
          "maturity": "contract",
          "implementation_refs": [
            "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION",
            "G3_PR"
          ],
          "canonical": "audit_projection",
          "gate_id": "G6_PRODUCTION_DATA",
          "gate_label": "G6 · Production Data",
          "sequence": 53,
          "node_label": "G6_PRODUCTION_DATA-N03",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/03-sync-projection-external-audit-event-projection.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/03-sync-projection-external-audit-event-projection.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-readback.json"
          ],
          "runbook": [
            "Load node descriptor sync-projection-external-audit-event-projection",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-053-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-053-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/03-sync-projection-external-audit-event-projection.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-053-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/sync_projection/external-audit-event-projection.node.json"
              ]
            },
            {
              "event_id": "ex-053-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/03-sync-projection-external-audit-event-projection.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-053",
              "revision": 53,
              "current_node_id": "sync-projection-external-audit-event-projection",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-f743a398",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        },
        {
          "node_id": "failure_recovery.unknown-write-reconciliation",
          "title": "Unknown Write Reconciliation",
          "description": "Require provider readback after an ambiguous write result before any retry or PASS decision.",
          "node_type": "gate",
          "family": "failure_recovery",
          "authority_boundary": "g2_required",
          "catalog_path": "core/node-architect/node-catalog/failure_recovery/unknown-write-reconciliation.node.json",
          "source_status": "proposed_registry_slot",
          "maturity": "experimental",
          "implementation_refs": [
            "core/node-architect/node-catalog/failure_recovery/unknown-write-reconciliation.node.json"
          ],
          "declared_gates": [
            "G2_EXECUTION"
          ],
          "canonical": "delivery_evidence",
          "gate_id": "G6_PRODUCTION_DATA",
          "gate_label": "G6 · Production Data",
          "sequence": 54,
          "node_label": "G6_PRODUCTION_DATA-N04",
          "artifacts": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/04-unknown-write-reconciliation.node-run.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/04-unknown-write-reconciliation.runbook.yaml"
          ],
          "reads": [
            "core/node-architect/node-catalog/**/*.node.json",
            "core/node-architect/node-registry.json",
            "core/node-architect/runtime-graph-registry.json",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml",
            ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-readback.json"
          ],
          "runbook": [
            "Load node descriptor failure_recovery.unknown-write-reconciliation",
            "Validate gate/evidence preconditions",
            "Execute or simulate node action",
            "Read back evidence and append run event",
            "Persist checkpoint/update node history"
          ],
          "taskcontroller_history": [
            {
              "event_id": "tc-054-admit",
              "type": "node_admitted",
              "actor": "TaskController",
              "outcome": "accepted",
              "evidence": [
                "core/node-architect/node-catalog/**/*.node.json"
              ]
            },
            {
              "event_id": "tc-054-project",
              "type": "history_projected",
              "actor": "TaskController",
              "outcome": "observed",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/04-unknown-write-reconciliation.node-run.json"
              ]
            }
          ],
          "executor_history": [
            {
              "event_id": "ex-054-start",
              "type": "executor_started",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "running",
              "evidence": [
                "core/node-architect/node-catalog/failure_recovery/unknown-write-reconciliation.node.json"
              ]
            },
            {
              "event_id": "ex-054-finish",
              "type": "executor_finished",
              "actor": "Hermes Mac / local_agent_sim",
              "outcome": "success",
              "evidence": [
                ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/nodes/04-unknown-write-reconciliation.runbook.yaml"
              ]
            }
          ],
          "checkpoints": [
            {
              "checkpoint_id": "cp-054",
              "revision": 54,
              "current_node_id": "failure_recovery.unknown-write-reconciliation",
              "next_node_id": "pending",
              "lease_owner": "hermes-mac-sim",
              "fencing_token": "fnc-dbba1fef",
              "status": "done"
            }
          ],
          "options": [
            "continue",
            "retry/self-remediate",
            "block for human authority",
            "mark not_applicable when gate conditional"
          ]
        }
      ],
      "gate_artifacts": [
        ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-approval.yaml",
        ".gwc/tasks/SCRUM-SIM-G0G6/g6/production-readback.json"
      ],
      "taskcontroller_history": [
        {
          "event_id": "tc-G6_PRODUCTION_DATA-open",
          "type": "gate_opened",
          "actor": "TaskController",
          "outcome": "running",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/"
          ]
        },
        {
          "event_id": "tc-G6_PRODUCTION_DATA-close",
          "type": "gate_closed",
          "actor": "TaskController",
          "outcome": "pass",
          "evidence": [
            ".gwc/tasks/SCRUM-SIM-G0G6/g6_production_data/gate-summary.json"
          ]
        }
      ],
      "executor_history": [
        {
          "event_id": "ex-G6_PRODUCTION_DATA-lease",
          "type": "executor_gate_session",
          "actor": "Hermes Mac / local_agent_sim",
          "outcome": "completed",
          "evidence": [
            "session://DW-OBS-ARCH-SIM-G0G6-20260823-R3/G6_PRODUCTION_DATA"
          ]
        }
      ]
    }
  ]
} satisfies SimRun;
