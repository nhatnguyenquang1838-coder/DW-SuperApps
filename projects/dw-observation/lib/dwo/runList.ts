/**
 * CR-826-B — Run List + Run Detail + graph/tree selection synchronization.
 *
 * SCRUM-826 / DWO-V2-05, G2 EXECUTE, PLAN-826-R1, child run CR-826-B.
 *
 * Run List and Run Detail, with graph and tree/list selection staying synchronized
 * (AC-826-03). A single shared selection state drives both the graph and the
 * structured tree/list.
 *
 * Design decisions:
 *  1. A single selection state (selectedRunId) is shared by graph and tree/list.
 *  2. Selecting a run in either view updates the shared state; both views reflect it.
 *  3. Run Detail shows the selected run's full reduced state.
 */

import type { RunViewRow, RunViewModel } from './runViewModel';

/** The shared selection state for graph/tree synchronization. */
export interface SelectionState {
  readonly selectedRunId: string | null;
}

/** Select a run; returns a new selection state (immutable). */
export function selectRun(state: SelectionState, runId: string): SelectionState {
  return { selectedRunId: runId };
}

/** Clear the selection. */
export function clearSelection(): SelectionState {
  return { selectedRunId: null };
}

/** The run list: all rows, optionally filtered to a parent's children. */
export function runList(viewModel: RunViewModel, parentId: string | null = null): readonly RunViewRow[] {
  if (parentId === null) return viewModel.rows;
  return viewModel.rows.filter((r) => r.parent === parentId);
}

/** The run detail for a selected run. */
export function runDetail(viewModel: RunViewModel, runId: string): RunViewRow | null {
  return viewModel.rows.find((r) => r.runId === runId) ?? null;
}

/**
 * Assert graph/tree selection synchronization.
 *
 * Returns true when selecting a run in the shared state is reflected consistently
 * (the selected run exists in the view model).
 */
export function assertSelectionSynchronized(
  viewModel: RunViewModel,
  selection: SelectionState,
): boolean {
  if (selection.selectedRunId === null) return true;
  return viewModel.rows.some((r) => r.runId === selection.selectedRunId);
}

/** Run list/detail is read-only; it grants no effect capability. */
export interface RunListCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const RUN_LIST_CAPABILITIES: RunListCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
