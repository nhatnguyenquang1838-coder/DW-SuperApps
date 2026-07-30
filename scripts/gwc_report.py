#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

GATE_ORDER = [
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
]

GATE_LABELS = {
    "G0_CONTEXT": "G0 — Context",
    "G1_ALIGNMENT": "G1 — Alignment",
    "G2_EXECUTION": "G2 — Execution",
    "G3_PR": "G3 — Draft PR",
    "G4_MERGE": "G4 — Merge",
    "G5_DEPLOY": "G5 — Deploy",
    "G6_PRODUCTION_DATA": "G6 — Production Data",
}

STATUS_COLORS = {
    "PASS": "#2e7d32",
    "FAIL": "#c62828",
    "READY": "#1565c0",
    "BLOCKED": "#e65100",
    "PENDING": "#616161",
    "COMPLETED": "#2e7d32",
    "APPROVED": "#2e7d32",
    "MERGED": "#1565c0",
    "DEPLOYED": "#2e7d32",
    "RUNNING": "#f9a825",
    "NOT_APPLICABLE": "#9e9e9e",
    "ACCEPTED": "#2e7d32",
    "REJECTED": "#c62828",
}


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


def find_task_dir(workspace: Path, task_id: str) -> Path:
    task_dir = workspace / ".gwc" / "tasks" / task_id
    if not task_dir.is_dir():
        raise ReportError(f"task not found: {task_id}")
    return task_dir


def discover_gates(task_dir: Path) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    gate_dir_map = {
        "G0_CONTEXT": "g0",
        "G1_ALIGNMENT": "g1",
        "G2_EXECUTION": "g2",
        "G3_PR": "g3",
        "G4_MERGE": "g4",
        "G5_DEPLOY": "g5",
        "G6_PRODUCTION_DATA": "g6",
    }
    for gate_id in GATE_ORDER:
        dir_name = gate_dir_map.get(gate_id, gate_id.lower())
        gate_dir = task_dir / dir_name
        if not gate_dir.is_dir():
            continue
        yaml_files = sorted(gate_dir.rglob("*.yaml"))
        md_files = sorted(gate_dir.rglob("*.md"))
        if not yaml_files and not md_files:
            continue
        gate_info = {
            "gate_id": gate_id,
            "label": GATE_LABELS.get(gate_id, gate_id),
            "yaml_artifacts": [],
            "md_artifacts": [],
            "status": "PENDING",
            "timestamp": None,
            "parsed": {},
        }
        for yf in yaml_files:
            rel = yf.relative_to(task_dir)
            try:
                data = load_yaml(yf)
                gate_info["yaml_artifacts"].append(
                    {
                        "path": str(rel),
                        "name": yf.name,
                        "size": yf.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            yf.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                        "data": data,
                    }
                )
            except Exception:
                gate_info["yaml_artifacts"].append(
                    {
                        "path": str(rel),
                        "name": yf.name,
                        "size": yf.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            yf.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                        "data": {},
                    }
                )
        for mf in md_files:
            rel = mf.relative_to(task_dir)
            gate_info["md_artifacts"].append(
                {
                    "path": str(rel),
                    "name": mf.name,
                    "size": mf.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        mf.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        gates.append(gate_info)
    return gates


def extract_gate_status(gate: dict[str, Any]) -> str:
    for a in gate["yaml_artifacts"]:
        data = a.get("data") or {}
        for key in ("status", "gate_outcome", "outcome", "result"):
            if key in data and isinstance(data[key], str):
                return data[key].upper()
        if "checks" in data and isinstance(data["checks"], list):
            all_pass = all(
                c.get("status", "").upper() == "PASS"
                for c in data["checks"]
                if isinstance(c, dict)
            )
            if all_pass and data["checks"]:
                return "PASS"
    return "PENDING"


def extract_gate_timestamp(gate: dict[str, Any]) -> str | None:
    for a in gate["yaml_artifacts"]:
        data = a.get("data") or {}
        for key in ("generated_at", "started_at_utc", "completed_at_utc", "decided_at"):
            if key in data and isinstance(data[key], str):
                return data[key][:19]
    return None


def enrich_gates(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for gate in gates:
        gate["status"] = extract_gate_status(gate)
        ts = extract_gate_timestamp(gate)
        if ts:
            gate["timestamp"] = ts
    return gates


def render_field_list(items: list[str], title: str) -> str:
    if not items:
        return ""
    return f"""
        <div class="field">
          <span class="field-label">{html.escape(title)}</span>
          <ul>{"".join(f"<li>{html.escape(item)}</li>" for item in items)}</ul>
        </div>"""


def render_yaml_fields(data: dict[str, Any], exclude_keys: set[str]) -> str:
    rows = ""
    for key, value in data.items():
        if key in exclude_keys:
            continue
        if isinstance(value, dict):
            rows += f"""
          <tr>
            <td class="key">{html.escape(key)}</td>
            <td>
              <table class="nested">
                {"".join(
                    f"<tr><td class='nk'>{html.escape(str(k))}</td><td>{html.escape(str(v)[:200])}</td></tr>"
                    for k, v in value.items()
                    if not isinstance(v, (dict, list))
                )}
              </table>
            </td>
          </tr>"""
        elif isinstance(value, list):
            rows += f"""
          <tr>
            <td class="key">{html.escape(key)}</td>
            <td><ul>{"".join(f"<li>{html.escape(str(item)[:200])}</li>" for item in value[:10])}</ul></td>
          </tr>"""
        else:
            rows += f"""
          <tr>
            <td class="key">{html.escape(key)}</td>
            <td>{html.escape(str(value)[:300])}</td>
          </tr>"""
    return rows


def render_gate_content(gate: dict[str, Any]) -> str:
    status = gate["status"]
    color = STATUS_COLORS.get(status, "#616161")
    badge = f'<span class="badge" style="background:{color}">{html.escape(status)}</span>'

    sections = ""

    for ya in gate["yaml_artifacts"]:
        data = ya.get("data") or {}
        if not data:
            continue
        artifact_type = data.get("artifact_type", ya["name"])
        exclude = {"schema_version", "artifact_type", "task_id", "repository", "base_ref", "base_sha", "scope_hash"}

        # Extract key human-readable fields
        title = artifact_type.replace("-", " ").title()
        key_fields = ""
        for k in ("status", "outcome", "result", "gate_outcome", "risk_class", "approval_status", "intake_status"):
            if k in data and isinstance(data[k], str):
                fc = STATUS_COLORS.get(data[k].upper(), "#616161")
                key_fields += f' <span class="badge" style="background:{fc}">{html.escape(data[k].upper())}</span>'

        # Extract problem statement / summary
        summary_text = ""
        for k in ("problem_statement", "problem", "summary", "rationale", "reason"):
            if k in data and isinstance(data[k], str) and data[k].strip():
                summary_text = data[k].strip()[:300]
                break

        # Extract decisions
        decisions = ""
        if "selected_option_id" in data:
            decisions += f"<p><strong>Selected:</strong> {html.escape(data['selected_option_id'])}</p>"
        if "rejected_option_ids" in data and isinstance(data["rejected_option_ids"], list):
            decisions += f"<p><strong>Rejected:</strong> {', '.join(html.escape(str(r)) for r in data['rejected_option_ids'])}</p>"

        # Extract authority boundaries
        auth_html = ""
        if "authority_boundaries" in data and isinstance(data["authority_boundaries"], dict):
            ab = data["authority_boundaries"]
            grants = ab.get("grants", [])
            excludes = ab.get("excludes", [])
            if grants:
                auth_html += f"<p><strong>Grants:</strong> {', '.join(html.escape(str(g)) for g in grants)}</p>"
            if excludes:
                auth_html += f"<p><strong>Excludes:</strong> {', '.join(html.escape(str(e)) for e in excludes)}</p>"

        # Extract excluded actions
        excluded_actions = ""
        if "excluded_actions" in data and isinstance(data["excluded_actions"], list):
            excluded_actions = f"<p><strong>Excluded actions:</strong> {', '.join(html.escape(str(a)) for a in data['excluded_actions'][:8])}</p>"

        # Extract validation results
        validation = ""
        if "validation" in data and isinstance(data["validation"], dict):
            for vk, vv in data["validation"].items():
                vc = STATUS_COLORS.get(str(vv).upper(), "#616161")
                validation += f' <span class="badge" style="background:{vc}">{html.escape(str(vk))}: {html.escape(str(vv))}</span>'

        # Extract result details
        result_details = ""
        if "result" in data and isinstance(data["result"], dict):
            for rk, rv in data["result"].items():
                if isinstance(rv, dict):
                    result_details += f"<p><strong>{html.escape(rk)}:</strong></p><ul>"
                    for rkk, rvv in rv.items():
                        rc = STATUS_COLORS.get(str(rvv).upper(), "#616161")
                        result_details += f'<li><span class="badge" style="background:{rc}">{html.escape(str(rvv))}</span> {html.escape(str(rkk))}</li>'
                    result_details += "</ul>"
                elif isinstance(rv, list):
                    result_details += f"<p><strong>{html.escape(rk)}:</strong></p><ul>"
                    for item in rv[:10]:
                        result_details += f"<li>{html.escape(str(item))}</li>"
                    result_details += "</ul>"
                else:
                    rc = STATUS_COLORS.get(str(rv).upper(), "#616161")
                    result_details += f'<p><span class="badge" style="background:{rc}">{html.escape(str(rv))}</span> <strong>{html.escape(rk)}</strong></p>'

        # Review lanes
        review = ""
        if "review" in data and isinstance(data["review"], dict):
            review_data = data["review"]
            if "lanes" in review_data and isinstance(review_data["lanes"], dict):
                review += "<p><strong>Review lanes:</strong></p><ul>"
                for lane, lstatus in review_data["lanes"].items():
                    lc = STATUS_COLORS.get(str(lstatus).upper(), "#616161")
                    review += f'<li><span class="badge" style="background:{lc}">{html.escape(str(lstatus))}</span> {html.escape(lane)}</li>'
                review += "</ul>"

        # Subagent distribution
        subagent = ""
        if "subagent_distribution_plan" in data and isinstance(data["subagent_distribution_plan"], dict):
            sap = data["subagent_distribution_plan"]
            if "task_decomposition" in sap and isinstance(sap["task_decomposition"], list):
                subagent += "<p><strong>Task decomposition:</strong></p><ul>"
                for td in sap["task_decomposition"]:
                    if isinstance(td, dict):
                        subagent += f"<li>{html.escape(td.get('task', str(td)))} → {html.escape(td.get('agent', 'unknown'))}</li>"
                    else:
                        subagent += f"<li>{html.escape(str(td))}</li>"
                subagent += "</ul>"

        # Options (for G1 brainstorming)
        options_html = ""
        if "options" in data and isinstance(data["options"], list):
            options_html += "<p><strong>Options considered:</strong></p><ul>"
            for opt in data["options"]:
                if isinstance(opt, dict):
                    oid = opt.get("option_id", "")
                    otitle = opt.get("title", "")
                    osummary = opt.get("summary", "")
                    selected = opt.get("option_id") == data.get("selected_option_id")
                    marker = " ✅" if selected else ""
                    options_html += f"<li><strong>{html.escape(oid)}: {html.escape(otitle)}</strong>{marker}<br><em>{html.escape(osummary[:200] if osummary else '')}</em></li>"
            options_html += "</ul>"

        # Acceptance criteria
        ac_html = ""
        if "acceptance_criteria" in data and isinstance(data["acceptance_criteria"], list):
            ac_html = render_field_list(data["acceptance_criteria"], "Acceptance Criteria")

        # Required next gate
        next_gate = ""
        if "required_next_gate" in data and isinstance(data["required_next_gate"], str):
            next_gate = f'<p><strong>Next gate:</strong> {html.escape(data["required_next_gate"])}</p>'
        if "next_gate" in data and isinstance(data["next_gate"], str):
            next_gate = f'<p><strong>Next gate:</strong> {html.escape(data["next_gate"])}</p>'

        # Risk class
        risk_class = ""
        if "risk_class" in data and isinstance(data["risk_class"], str):
            rc = STATUS_COLORS.get(data["risk_class"].upper(), "#616161")
            risk_class = f'<p><strong>Risk class:</strong> <span class="badge" style="background:{rc}">{html.escape(data["risk_class"])}</span></p>'

        # Checks (for preflight)
        checks_html = ""
        if "checks" in data and isinstance(data["checks"], list):
            checks_html = "<p><strong>Checks:</strong></p><ul>"
            for check in data["checks"]:
                if isinstance(check, dict):
                    cs = check.get("status", "").upper()
                    cc = STATUS_COLORS.get(cs, "#616161")
                    checks_html += f'<li><span class="badge" style="background:{cc}">{html.escape(cs)}</span> {html.escape(check.get("id", check.get("code", "")))} — {html.escape(check.get("message", "")[:200])}</li>'
            checks_html += "</ul>"

        # Post-merge actions
        post_merge = ""
        if "post_merge_required_actions" in data and isinstance(data["post_merge_required_actions"], list):
            if data["post_merge_required_actions"]:
                post_merge = render_field_list(data["post_merge_required_actions"], "Post-merge actions")

        # Notes
        notes_html = ""
        if "notes" in data and isinstance(data["notes"], list):
            notes_html = render_field_list(data["notes"], "Notes")

        # Excluded actions (for G4/G5)
        excluded = ""
        if "excluded_actions" in data and isinstance(data["excluded_actions"], list):
            excluded = render_field_list(data["excluded_actions"], "Excluded actions")

        # Authorized actions
        authorized = ""
        if "authorized_actions" in data and isinstance(data["authorized_actions"], list):
            authorized = render_field_list(data["authorized_actions"], "Authorized actions")

        # Changed files
        changed_files = ""
        if "changed_files" in data and isinstance(data["changed_files"], list):
            changed_files = render_field_list(data["changed_files"][:15], "Changed files")

        # Implementation decisions
        impl_decisions = ""
        if "main_implementation_decisions" in data and isinstance(data["main_implementation_decisions"], list):
            impl_decisions = render_field_list(data["main_implementation_decisions"], "Key decisions")

        # Scope hash
        scope_hash = ""
        if "scope_hash" in data and isinstance(data["scope_hash"], str):
            scope_hash = f'<p><strong>Scope hash:</strong> <code>{html.escape(data["scope_hash"][:32])}…</code></p>'

        # Task info
        task_info = ""
        if "task" in data and isinstance(data["task"], dict):
            td = data["task"]
            task_info = f'<p><strong>Task:</strong> {html.escape(td.get("id", ""))} — {html.escape(td.get("title", ""))}</p>'

        # Problem / desired outcome
        problem = ""
        if "problem_statement" in data and isinstance(data["problem_statement"], str):
            problem = f'<p><strong>Problem:</strong> {html.escape(data["problem_statement"][:300])}</p>'
        if "desired_outcome" in data and isinstance(data["desired_outcome"], str):
            problem += f'<p><strong>Desired outcome:</strong> {html.escape(data["desired_outcome"][:300])}</p>'

        # Stakeholders
        stakeholders = ""
        if "stakeholders" in data and isinstance(data["stakeholders"], dict):
            sh = data["stakeholders"]
            stakeholders = f'<p><strong>Stakeholders:</strong> Requester: {html.escape(sh.get("requester", ""))}, Affected: {", ".join(html.escape(str(a)) for a in sh.get("affected", []))}</p>'

        # Constraints
        constraints = ""
        if "constraints" in data and isinstance(data["constraints"], list):
            constraints = render_field_list(data["constraints"], "Constraints")

        # Assumptions
        assumptions = ""
        if "assumptions" in data and isinstance(data["assumptions"], list):
            assumptions = render_field_list(data["assumptions"], "Assumptions")

        # Risks
        risks = ""
        if "risks" in data and isinstance(data["risks"], list):
            risks = "<p><strong>Risks:</strong></p><ul>"
            for r in data["risks"][:5]:
                if isinstance(r, dict):
                    risks += f'<li><strong>{html.escape(r.get("id", ""))}</strong> ({html.escape(r.get("impact", ""))}): {html.escape(r.get("description", "")[:200])}</li>'
            risks += "</ul>"

        # Unresolved questions
        unresolved = ""
        if "unresolved_questions" in data and isinstance(data["unresolved_questions"], list):
            unresolved = render_field_list(data["unresolved_questions"], "Unresolved questions")

        # User decision
        user_decision = ""
        if "user_decision" in data and isinstance(data["user_decision"], dict):
            ud = data["user_decision"]
            user_decision = f'<p><strong>User decision:</strong> Actor: {html.escape(ud.get("actor", ""))}, Decided at: {html.escape(ud.get("decided_at", ""))}, Source: {html.escape(ud.get("source", ""))}, Explicit: {html.escape(str(ud.get("explicit", "")))}</p>'

        # Verification state
        verification = ""
        if "verification" in data and isinstance(data["verification"], dict):
            vd = data["verification"]
            verification = f'<p><strong>Verification:</strong> State: {html.escape(vd.get("state", ""))}, Reason: {html.escape(vd.get("reason", "")[:200])}</p>'

        # Merge commit
        merge_commit = ""
        if "merge_commit_sha" in data:
            merge_commit = f'<p><strong>Merge commit:</strong> <code>{html.escape(str(data["merge_commit_sha"])[:16])}…</code></p>'

        # G3 review lanes
        review_lanes = ""
        if "review" in data and isinstance(data["review"], dict):
            rd = data["review"]
            if "lanes" in rd and isinstance(rd["lanes"], dict):
                review_lanes = "<p><strong>Review lanes:</strong></p><ul>"
                for lane, lstatus in rd["lanes"].items():
                    lc = STATUS_COLORS.get(str(lstatus).upper(), "#616161")
                    review_lanes += f'<li><span class="badge" style="background:{lc}">{html.escape(str(lstatus))}</span> {html.escape(lane)}</li>'
                review_lanes += "</ul>"

        # Build the section
        sections += f"""
        <div class="artifact-section">
          <h4>{html.escape(title)} {badge}{key_fields}</h4>
          {task_info}
          {problem}
          {summary_text and f'<p class="summary">{html.escape(summary_text)}</p>' or ''}
          {decisions}
          {risk_class}
          {next_gate}
          {scope_hash}
          {user_decision}
          {auth_html}
          {excluded_actions}
          {authorized}
          {excluded}
          {checks_html}
          {validation}
          {result_details}
          {changed_files}
          {impl_decisions}
          {options_html}
          {review_lanes or review}
          {subagent}
          {ac_html}
          {constraints}
          {assumptions}
          {risks}
          {unresolved}
          {notes_html}
          {post_merge}
          {merge_commit}
          {verification}
        </div>"""

    for ma in gate["md_artifacts"]:
        sections += f"""
        <div class="artifact-section">
          <h4>{html.escape(ma['name'])}</h4>
          <p class="file-ref">Markdown artifact: <code>{html.escape(ma['path'])}</code></p>
        </div>"""

    if not sections:
        sections = "<p>No parsed artifacts.</p>"

    return sections


def render_progress(gates: list[dict[str, Any]]) -> str:
    completed = sum(1 for g in gates if g["status"] not in ("PENDING",))
    total = len(gates)
    pct = int((completed / total) * 100) if total > 0 else 0
    return f"""
    <div class="progress-bar">
      <div class="progress-fill" style="width:{pct}%"></div>
    </div>
    <p class="progress-label">{completed}/{total} gates completed ({pct}%)</p>"""


def render_html(task_id: str, gates: list[dict[str, Any]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    overall_status = "PASS" if all(g["status"] == "PASS" for g in gates) else "PARTIAL"
    overall_color = STATUS_COLORS.get(overall_status, "#616161")

    progress = render_progress(gates)

    gate_sections = ""
    for gate in gates:
        gate_sections += f"""
        <div class="gate-card">
          <div class="gate-header">
            <h3>{html.escape(gate['label'])}</h3>
            {f'<span class="badge" style="background:{STATUS_COLORS.get(gate["status"], "#616161")}">{html.escape(gate["status"])}</span>' if gate["status"] else ""}
            {f'<span class="timestamp">{html.escape(gate["timestamp"])}</span>' if gate["timestamp"] else ""}
          </div>
          <div class="gate-body">
            {render_gate_content(gate)}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GWC Dashboard — {html.escape(task_id)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f5f5;
    color: #212121;
    line-height: 1.6;
    padding: 2rem;
    max-width: 1100px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 1.75rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
    color: #1a1a1a;
  }}
  .subtitle {{
    color: #757575;
    font-size: 0.9rem;
    margin-bottom: 1.5rem;
  }}
  .overview {{
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
  }}
  .overview .badge {{
    font-size: 0.85rem;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    color: #fff;
    font-weight: 600;
  }}
  .overview .task-id {{
    font-family: monospace;
    font-size: 0.95rem;
  }}
  .timestamp {{
    font-size: 0.8rem;
    color: #9e9e9e;
    margin-left: 0.5rem;
  }}
  .progress-bar {{
    background: #e0e0e0;
    border-radius: 8px;
    height: 12px;
    overflow: hidden;
    margin: 0.5rem 0;
  }}
  .progress-fill {{
    background: #1565c0;
    height: 100%;
    border-radius: 8px;
    transition: width 0.3s ease;
  }}
  .progress-label {{
    font-size: 0.8rem;
    color: #757575;
  }}
  .gate-card {{
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    margin-bottom: 1rem;
    overflow: hidden;
  }}
  .gate-header {{
    padding: 0.75rem 1rem;
    background: #fafafa;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  .gate-header h3 {{
    font-size: 1rem;
    font-weight: 600;
    flex: 1;
  }}
  .gate-body {{
    padding: 1rem;
  }}
  .badge {{
    display: inline-block;
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    color: #fff;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }}
  .artifact-section {{
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #f0f0f0;
  }}
  .artifact-section:last-child {{
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }}
  .artifact-section h4 {{
    font-size: 0.9rem;
    color: #616161;
    margin-bottom: 0.5rem;
  }}
  .field {{
    margin-bottom: 0.5rem;
  }}
  .field-label {{
    font-weight: 600;
    font-size: 0.85rem;
    color: #424242;
  }}
  ul {{
    margin: 0.25rem 0 0.5rem 1.5rem;
    padding: 0;
  }}
  li {{
    margin: 0.15rem 0;
    font-size: 0.85rem;
  }}
  p {{
    margin: 0.4rem 0;
    font-size: 0.85rem;
  }}
  .summary {{
    background: #f9f9f9;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-style: italic;
    font-size: 0.85rem;
  }}
  .key {{
    font-weight: 600;
    color: #424242;
    width: 200px;
    white-space: nowrap;
  }}
  table.nested {{
    font-size: 0.8rem;
  }}
  table.nested td {{
    padding: 0.1rem 0.5rem;
    border: none;
  }}
  .nk {{
    font-weight: 600;
    color: #616161;
    width: 150px;
  }}
  code {{
    background: #f0f0f0;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    font-size: 0.8rem;
  }}
  .file-ref {{
    color: #757575;
    font-size: 0.8rem;
  }}
  .gate-card h3 {{
    font-size: 1rem;
  }}
</style>
</head>
<body>
  <h1>GWC Dashboard</h1>
  <p class="subtitle">Task <span class="task-id">{html.escape(task_id)}</span> &middot; Generated {html.escape(now)}</p>
  <div class="overview">
    <span class="badge" style="background:{overall_color}">{html.escape(overall_status)}</span>
    <span>{len(gates)} gate(s)</span>
    {progress}
  </div>
  {gate_sections}
</body>
</html>"""


def cmd_report(args: argparse.Namespace) -> int:
    workspace = resolve_workspace_path(args.workspace)
    task_dir = find_task_dir(workspace, args.task)
    gates = discover_gates(task_dir)
    if not gates:
        raise ReportError(f"no gate artifacts found for task: {args.task}")
    gates = enrich_gates(gates)
    report_html = render_html(args.task, gates)
    output_path = task_dir / "report.html"
    output_path.write_text(report_html, encoding="utf-8")
    print(f"Dashboard written to {output_path}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="dw gwc report",
        description="Generate a human-readable HTML dashboard from GWC task artifacts",
    )
    result.add_argument("task", help="Task ID (e.g. SCRUM-119)")
    result.add_argument(
        "--workspace",
        default=".",
        help="Workspace root path (default: current directory)",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(cmd_report(args))
    except (ReportError, ValueError, KeyError) as exc:
        print(f"dw-gwc-report: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())