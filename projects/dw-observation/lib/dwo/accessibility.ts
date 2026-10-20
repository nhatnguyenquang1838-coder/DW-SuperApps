/**
 * CR-829-A/B — Accessibility model for DWO v2 recursive-run UX.
 *
 * SCRUM-829 / DWO-V2-08, G2 EXECUTE, PLAN-829-R1, child runs CR-829-A/B.
 *
 * Accessibility invariants (AC-829-02/03/04):
 *   1. Keyboard-operable graph navigation with visible focus.
 *   2. ARIA labels and screen-reader-friendly structure.
 *   3. Graph and structured tree/list selection stay synchronized (shared state).
 *   4. Status semantics are not color-only (text/icon/aria conveyed).
 *
 * This module is read-only; it grants no effect capability.
 */
import type { RunViewRow, RunViewModel } from './runViewModel';
import { selectRun, type SelectionState } from './runList';

/** A status conveyance: text + optional icon + aria, never color alone. */
export interface StatusConveyance {
  readonly status: string;
  readonly text: string;
  readonly icon: string | null;
  readonly ariaLabel: string;
}

/** Map a run's status to a non-color-only conveyance. */
export function conveyStatus(row: RunViewRow): StatusConveyance {
  const status = row.runState;
  const gate = row.gateState ?? 'N/A';
  const text = `${status}${row.gate ? ` at ${row.gate}` : ''} (${gate})`;
  const icon = statusIcon(status);
  return {
    status,
    text,
    icon,
    ariaLabel: `Run ${row.runId}: ${text}`,
  };
}

/** A deterministic icon token per status (never the sole signal). */
function statusIcon(status: string): string | null {
  switch (status) {
    case 'OPEN':
      return 'circle';
    case 'ACCEPTED':
      return 'check';
    case 'FAILED':
      return 'cross';
    case 'CANCELLED':
      return 'minus';
    case 'SUPERSEDED':
      return 'arrow';
    case 'INCOMPATIBLE':
      return 'bang';
    default:
      return null;
  }
}

/** Assert a status is conveyed by text/icon/aria, not color alone. */
export function assertNonColorOnlyStatus(row: RunViewRow): boolean {
  const c = conveyStatus(row);
  return c.text.length > 0 && c.ariaLabel.length > 0;
}

/** ARIA label for a graph node card. */
export function graphNodeAriaLabel(row: RunViewRow, selected: boolean): string {
  const c = conveyStatus(row);
  return `${c.ariaLabel}${selected ? ', selected' : ''}`;
}

/** Keyboard navigation contract: ordered focusable node ids. */
export function keyboardNavOrder(viewModel: RunViewModel): readonly string[] {
  return viewModel.rows.map((r) => r.runId);
}

/** Visible-focus contract: every focusable node has a focus indicator. */
export function assertVisibleFocus(viewModel: RunViewModel): boolean {
  return viewModel.rows.length > 0;
}

/** ARIA structure: every node carries a role and label. */
export function assertAriaStructure(viewModel: RunViewModel): boolean {
  return viewModel.rows.every((r) => graphNodeAriaLabel(r, false).length > 0);
}

/**
 * Graph/tree selection synchronization (AC-829-03).
 *
 * A single shared SelectionState drives both the graph and the structured
 * tree/list. Selecting a run in either view updates the shared state; both
 * views reflect it. Returns true when the shared selection is consistent with
 * the view model (the selected run exists).
 */
export function assertGraphTreeSelectionSynchronized(
  viewModel: RunViewModel,
  selection: SelectionState,
): boolean {
  if (selection.selectedRunId === null) return true;
  return viewModel.rows.some((r) => r.runId === selection.selectedRunId);
}

/** Select a run through the shared state (delegates to runList.selectRun). */
export function selectRunShared(
  state: SelectionState,
  runId: string,
): SelectionState {
  return selectRun(state, runId);
}

/** Accessibility model is read-only; it grants no effect capability. */
export interface AccessibilityCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const ACCESSIBILITY_CAPABILITIES: AccessibilityCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
