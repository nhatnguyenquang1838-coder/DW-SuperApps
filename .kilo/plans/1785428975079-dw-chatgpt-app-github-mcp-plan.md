# Plan: Add GitHub Git-Capabilities to dw-chatgpt-app MCP + Cockpit Widget

## Goal
Extend `projects/dw-chatgpt-app` so ChatGPT and Codex can:
1. Provide a GitHub token (client → MCP server, session-scoped, never echoed).
2. Query PR list, PR detail, workflow runs, and workflow run status via new MCP tools.
3. View results inside the existing cockpit HTML widget returned as `text/html;profile=mcp-app`.

## Current State
- `projects/dw-chatgpt-app` is an MCP server (`@modelcontextprotocol/sdk`) serving one widget resource (`ui://dw-super/cockpit.html`) and two tools (`get_dw_super_state`, `record_dw_super_action`).
- The cockpit is a static HTML string embedded in `src/server.ts`, rendered with hardcoded `sample-state.ts` data.
- Buttons send `DW_SUPER_ACTION` messages back into the chat via `window.openai.sendFollowUpMessage` / `ui/message`.
- No GitHub API integration exists yet.
- `context7` MCP pattern in this repo uses namespaced tool names (`mcp__context7__resolve_library_id`, `mcp__context7__get_library_docs`); our new tools should follow the same `mcp__<server>__<tool>` convention for ChatGPT/Codex discoverability.

## Constraints
- Read-only GitHub access only. No push, merge, comment, or write operations in this scope.
- Token must not be logged, repeated, stored to disk, or returned in tool output.
- Token storage is server-side session memory only; lost on server restart.
- Widget stays a single self-contained HTML string served as one MCP resource.
- Keep existing `get_dw_super_state` and `record_dw_super_action` behavior unchanged (except enriched state data).

## Implementation Plan

### 1. GitHub token setup tool
Add `mcp__dw_super__configure_github` (read-only helper).
- Input: `{ token: string }`
- Behavior: store token in server-side session map keyed by session id from the MCP transport. Return `{ configured: true }`.
- Security: redact token in logs. Never include token in `structuredContent` or `content`.
- If the same session calls again, rotate token silently.

### 2. GitHub read-only MCP tools
Add four tools, all read-only, all requiring prior `configure_github` success for the session. Return minimal shapes suitable for widget rendering.

**Tool: `mcp__dw_super__github_list_prs`**
- Input: `{ owner: string, repo: string, state?: "open"|"closed"|"all", per_page?: number, page?: number }`
- Output: `{ items: Array<{ number, title, state, user, created_at, updated_at, url }>, total_count }`
- Uses `GET /repos/{owner}/{repo}/pulls`.

**Tool: `mcp__dw_super__github_get_pr`**
- Input: `{ owner: string, repo: string, pull_number: number }`
- Output: `{ number, title, state, merged, user, created_at, updated_at, body, url, additions, deletions, changed_files }`
- Uses `GET /repos/{owner}/{repo}/pulls/{pull_number}`.

**Tool: `mcp__dw_super__github_list_workflow_runs`**
- Input: `{ owner: string, repo: string, workflow_id?: string, branch?: string, per_page?: number, page?: number }`
- Output: `{ items: Array<{ id, workflow_id, workflow_name, status, conclusion, head_branch, head_sha, created_at, url }>, total_count }`
- Uses `GET /repos/{owner}/{repo}/actions/runs` (filter by `workflow_id` query param when provided).

**Tool: `mcp__dw_super__github_get_workflow_run`**
- Input: `{ owner: string, repo: string, run_id: number }`
- Output: `{ id, workflow_id, workflow_name, status, conclusion, head_branch, head_sha, event, created_at, updated_at, url, jobs: Array<{ id, name, status, conclusion, started_at, completed_at }> }`
- Uses `GET /repos/{owner}/{repo}/actions/runs/{run_id}` and `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`.

### 3. State schema and sample-state extension
Extend `schemas/task-state.schema.json`, `fixtures/sample-task-state.json`, and `src/sample-state.ts` with optional GitHub context fields:
- `github_configured: boolean`
- `github_repositories: Array<{ owner, repo, last_checked_at, prs_total, open_prs, last_workflow }>`
- `github_errors: Array<{ owner, repo, message }>`

### 4. Cockpit widget UI additions
Update the embedded HTML string in `src/server.ts` and the standalone `widget/dw-super-cockpit.html`:

**New card: "🐙 GitHub status"**
- Two sub-sections: "Pull Requests" and "Workflows".
- Each shows owner/repo, counts, status badges, and clickable links.
- When no data is loaded, show a CTA: "Connect GitHub" that emits `DW_SUPER_ACTION configure_github` with a placeholder for the token (the actual token entry is out of widget scope; the assistant handles token collection via the `configure_github` tool).

**New buttons in Human actions card**
- `refresh_github`
- `check_prs`
- `check_workflows`

Button clicks send `DW_SUPER_ACTION` messages like:
```
DW_SUPER_ACTION github_list_prs
owner: nhatnguyenquang1838-coder
repo: DW-SuperApps
state: open
```

The assistant then calls the matching MCP tool, receives structured data, and the widget updates via `ui/notifications/tool-result`.

### 5. `get_dw_super_state` enrichment
Change `get_dw_super_state` so `structuredContent` can include live `github_*` fields when the assistant has already queried GitHub in the same conversation. The tool itself stays read-only; it just returns whatever state the conversation has produced. This matches the existing pattern where the widget is a projection of assistant-side tool results.

### 6. Documentation
Add `docs/GITHUB_MCP.md` covering:
- Tool naming convention (`mcp__dw_super__github_*`).
- Token flow: `configure_github` → session storage → read-only tools.
- Read-only boundary and prohibited actions.
- Error handling: 401/403 → `github_errors` state; rate-limit backoff note.
- Widget integration: how button actions map to tools and how results render.

## Data Flow
```
ChatGPT / Codex
  → widget button click
  → ui/message / sendFollowUpMessage
  → assistant calls mcp__dw_super__github_*
  → MCP server calls GitHub REST API with session token
  → assistant receives structured data
  → widget updated via ui/notifications/tool-result
```

## Failure Modes
- Token missing / invalid: tool returns `{ error: "GITHUB_TOKEN_MISSING" }` with instruction to run `configure_github`.
- GitHub rate limit: tool returns `{ error: "RATE_LIMITED", retry_after_seconds }`; widget shows warning.
- Network failure: tool returns `{ error: "NETWORK_ERROR" }`; widget shows retry button.
- Repo not found (404): tool returns `{ error: "NOT_FOUND" }`.

## Validation
- `npm run typecheck` in `projects/dw-chatgpt-app`.
- Run `npm run dev` and hit `/mcp` with manual JSON-RPC for `configure_github`, `github_list_prs`, `github_get_pr`, `github_list_workflow_runs`, `github_get_workflow_run`.
- Verify widget renders PR and workflow sections via `npm run preview`.
- Confirm token never appears in server logs or tool responses.

## Out of Scope
- GitHub write operations (PR comments, merges, status updates).
- Persistent token storage (database, file, env).
- OAuth flow; static token by client design.
- Codex-specific UI differences; widget is shared.

## Open Question
- Token entry UX: should the widget include a password field, or should the assistant collect the token via chat? Recommended answer: assistant collects the token via chat and calls `configure_github`; the widget only shows status. This avoids placing a secret input inside an iframe and matches the existing "buttons send intent, assistant executes" pattern.
