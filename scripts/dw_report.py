#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from dw_project_targets import ProjectTargetError, find_runtime_project
except ModuleNotFoundError:
    from scripts.dw_project_targets import ProjectTargetError, find_runtime_project

ROOT = Path(__file__).resolve().parents[1]


class ReportError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReportError(f"missing artifact: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError as exc:
        raise ReportError("PyYAML is required") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ReportError(f"expected YAML mapping: {path}")
    return data


def resolve_workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / value
    return path.resolve()


def find_system(system_id: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ReportError("PyYAML is required") from exc
    workspace_path = ROOT / "workspace.yaml"
    data = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    try:
        return find_runtime_project(data, system_id)
    except ProjectTargetError as exc:
        raise ReportError(str(exc)) from exc


def render_field(title: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        items = []
        for item in value:
            if isinstance(item, dict):
                parts = []
                for k, v in item.items():
                    if isinstance(v, list) and not v:
                        continue
                    parts.append(f"{k}: {v}")
                items.append(", ".join(parts))
            else:
                items.append(str(item))
        value = "\n".join(f"- {item}" for item in items)
    elif isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, list) and not v:
                continue
            parts.append(f"{k}: {v}")
        value = ", ".join(parts)
    return f"## {title}\n\n{value}\n\n"


def render_checks(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return ""
    lines = ["| ID | Status | Code | Message | Evidence |", "|---|---|---|---|---|"]
    for check in checks:
        lines.append(
            f"| {check.get('id', '')} | {check.get('status', '')} | {check.get('code', '')} | {check.get('message', '')} | {check.get('evidence', '')} |"
        )
    return "\n".join(lines) + "\n"


def render_options(options: list[dict[str, Any]], recommended: str) -> str:
    if not options:
        return ""
    lines = []
    for opt in options:
        opt_id = opt.get("id", "")
        title = opt.get("title", "")
        desc = opt.get("description", "")
        benefits = opt.get("benefits", [])
        tradeoffs = opt.get("tradeoffs", [])
        risks = opt.get("risks", [])
        constraint_fit = opt.get("constraint_fit", "")
        lines.append(f"### {opt_id}: {title}")
        if desc:
            lines.append(f"\n{desc}\n")
        if benefits:
            lines.append("**Benefits:**\n" + "\n".join(f"- {b}" for b in benefits) + "\n")
        if tradeoffs:
            lines.append("**Tradeoffs:**\n" + "\n".join(f"- {t}" for t in tradeoffs) + "\n")
        if risks:
            lines.append("**Risks:**\n" + "\n".join(f"- {r}" for r in risks) + "\n")
        if constraint_fit:
            lines.append(f"**Constraint fit:** {constraint_fit}\n")
        if opt_id == recommended:
            lines.append("**Recommendation:** ✅ Recommended\n")
        lines.append("")
    return "\n".join(lines)


def render_subagent_plan(plan: dict[str, Any]) -> str:
    if not plan:
        return ""
    lines = ["## Subagent Distribution Plan\n"]
    task_decomp = plan.get("task_decomposition", [])
    if task_decomp:
        lines.append("### Task Decomposition\n")
        for task in task_decomp:
            lines.append(f"- **{task.get('sub_task_id', '')}**: {task.get('description', '')}")
        lines.append("")
    agent_alloc = plan.get("agent_allocation", [])
    if agent_alloc:
        lines.append("### Agent Allocation\n")
        for agent in agent_alloc:
            lines.append(
                f"- **{agent.get('sub_task_id', '')}** → `{agent.get('skill_id', '')}` ({agent.get('agent_type', '')})"
            )
        lines.append("")
    exec_order = plan.get("execution_order", [])
    if exec_order:
        lines.append("### Execution Order\n")
        lines.append(" → ".join(f"`{step}`" for step in exec_order) + "\n")
    summary = plan.get("summary", "")
    if summary:
        lines.append(f"**Summary:** {summary}\n")
    return "\n".join(lines)


def build_g1_report(workspace: Path) -> str:
    g1_dir = workspace / "g1"
    intake = load_yaml(g1_dir / "intake" / "g1-intake-brief.yaml")
    options = load_yaml(g1_dir / "brainstorming" / "g1-options.yaml")
    preflight = load_yaml(g1_dir / "preflight" / "g1-preflight-report.yaml")
    decision = load_yaml(g1_dir / "decision" / "g1-decision-record.yaml")

    trace = intake.get("trace", {})
    problem = intake.get("problem", {})
    scope = intake.get("scope", {})
    constraints = intake.get("constraints", [])
    assumptions = intake.get("assumptions", [])
    risks = intake.get("risks", [])
    acceptance = intake.get("acceptance_criteria", [])
    unresolved = intake.get("unresolved_questions", [])
    status = intake.get("status", "")

    recommended = options.get("recommended_option_id", "")
    options_list = options.get("options", [])
    options_status = options.get("status", "")

    checks = preflight.get("checks", [])
    risk_class = preflight.get("risk_class", "")
    required_gate = preflight.get("required_gate", "")
    blockers = preflight.get("blockers", [])
    outcome = preflight.get("outcome", "")

    selected = decision.get("selected_option_id", "")
    user_decision = decision.get("user_decision", {})
    rationale = decision.get("rationale", "")
    rejected = decision.get("rejected_option_ids", [])
    ac_refs = decision.get("acceptance_criteria_refs", [])
    scope_hash = decision.get("scope_hash", "")
    gate_outcome = decision.get("g1_gate_outcome", "")
    authority = decision.get("authority_boundaries", {})
    subagent = decision.get("subagent_distribution_plan", {})
    decision_status = decision.get("status", "")

    lines = [
        "# G1 Alignment Report",
        "",
        f"**Project:** {trace.get('project_id', '')}",
        f"**Repository:** {trace.get('repository', '')}",
        f"**Task ID:** {trace.get('task_id', '')}",
        f"**Base SHA:** {trace.get('base_sha', '')}",
        f"**Generated at:** {intake.get('generated_at', '')}",
        "",
        "---",
        "",
        "## Intake",
        "",
        f"**Status:** {status}",
        "",
        f"### Problem\n\n{problem.get('statement', '')}\n\n",
        f"**Why now:** {problem.get('why_now', '')}\n\n",
        f"### Desired Outcome\n\n{intake.get('desired_outcome', '')}\n\n",
        f"### Stakeholders\n\n- Requester: {intake.get('stakeholders', {}).get('requester', '')}\n- Affected: {', '.join(intake.get('stakeholders', {}).get('affected', []))}\n\n",
        "### Scope\n\n",
        f"**In scope:**\n" + "\n".join(f"- {s}" for s in scope.get("in_scope", [])) + "\n\n",
        f"**Non-goals:**\n" + "\n".join(f"- {s}" for s in scope.get("non_goals", [])) + "\n\n",
        "### Constraints\n\n" + "\n".join(f"- {c}" for c in constraints) + "\n\n" if constraints else "",
        "### Assumptions\n\n" + "\n".join(f"- {a}" for a in assumptions) + "\n\n" if assumptions else "",
        "### Risks\n\n" + "\n".join(f"- **{r.get('id', '')}** ({r.get('impact', '')}): {r.get('description', '')}" for r in risks) + "\n\n" if risks else "",
        "### Acceptance Criteria\n\n" + "\n".join(f"- **{c.get('id', '')}**: {c.get('statement', '')}" for c in acceptance) + "\n\n" if acceptance else "",
        f"### Unresolved Questions\n\n{', '.join(unresolved)}\n\n" if unresolved else "",
        "---",
        "",
        "## Options",
        "",
        f"**Status:** {options_status}",
        f"**Recommended:** {recommended}",
        "",
        render_options(options_list, recommended),
        "---",
        "",
        "## Preflight",
        "",
        f"**Risk class:** {risk_class}",
        f"**Required next gate:** {required_gate}",
        f"**Outcome:** {outcome}",
        "",
        "### Checks\n\n" + render_checks(checks) if checks else "",
        f"### Blockers\n\n{', '.join(blockers)}\n\n" if blockers else "",
        "---",
        "",
        "## Decision",
        "",
        f"**Status:** {decision_status}",
        f"**Selected option:** {selected}",
        f"**Gate outcome:** {gate_outcome}",
        "",
        f"### Rationale\n\n{rationale}\n\n",
        f"### User Decision\n\n- Actor: {user_decision.get('actor', '')}\n- Decided at: {user_decision.get('decided_at', '')}\n- Source: {user_decision.get('source', '')}\n- Explicit: {user_decision.get('explicit', '')}\n\n",
        f"### Rejected Options\n\n{', '.join(rejected)}\n\n" if rejected else "",
        f"### Acceptance Criteria Refs\n\n{', '.join(ac_refs)}\n\n" if ac_refs else "",
        f"### Scope Hash\n\n`{scope_hash}`\n\n",
        "### Authority Boundaries\n\n",
        f"**Grants:** {', '.join(authority.get('grants', [])) or 'none'}\n\n",
        f"**Excluded:**\n" + "\n".join(f"- {e}" for e in authority.get("excluded", [])) + "\n\n",
        render_subagent_plan(subagent),
        "---",
        "",
        "## Next Steps",
        "",
        "- G2 planning may start only from an accepted G1 decision.",
        "- Repository writes remain unauthorized until a valid G2 execution envelope is approved.",
        "- G4 merge, G5 deploy, and G6 production remain separate human gates.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def cmd_report(args: argparse.Namespace) -> int:
    if args.gate.lower() != "g1":
        raise ReportError(f"unsupported gate: {args.gate}; only g1 is supported")
    workspace = resolve_workspace_path(args.workspace)
    g1_dir = workspace / "g1"
    if not g1_dir.is_dir():
        raise ReportError(f"not a G1 workspace: {workspace}")
    report = build_g1_report(workspace)
    print(report)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw report", description="GWC artifact reports")
    result.add_argument("gate", choices=["g1"])
    result.add_argument("--workspace", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(cmd_report(args))
    except (ReportError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"dw-report: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
