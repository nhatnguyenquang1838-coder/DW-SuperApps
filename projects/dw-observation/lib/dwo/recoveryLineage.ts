/**
 * CR-827-B — Recovery lineage.
 *
 * SCRUM-827 / DWO-V2-06, G2 EXECUTE, PLAN-827-R1, child run CR-827-B.
 *
 * Recovery lineage tracks retry, rerun, replan, restart, supersession and
 * reset-derived-state generations. Generations are APPEND-ONLY and IMMUTABLE;
 * they remain navigable from any generation back to its root (AC-827-03).
 *
 * Design decisions:
 *  1. A generation is created by append; the returned object is frozen and never
 *     mutated after creation.
 *  2. Each generation carries a parent link; the root has parentGeneration null.
 *  3. navigateLineage walks parent links to the root, returning the ordered path.
 *  4. Cycle guard (GPT review + @taskme AC): lineages are append-only/immutable,
 *     so a cycle means the historical data is CORRUPTED. navigateLineage must
 *     FAIL CLOSED by throwing — never return a partial path or []. The guard
 *     covers multi-node cycles (A->B->A) AND self-referential parents
 *     (parentGeneration pointing at itself).
 */

/** The recovery generation kinds. */
export type RecoveryKind =
  | 'RETRY'
  | 'RERUN'
  | 'REPLAN'
  | 'RESTART'
  | 'SUPERSESSION'
  | 'RESET_DERIVED_STATE';

/** A single immutable recovery generation. */
export interface RecoveryGeneration {
  readonly id: string;
  readonly runId: string;
  readonly kind: RecoveryKind;
  readonly parentGeneration: string | null;
}

/** Input to create a new recovery generation. */
export interface RecoveryGenerationInput {
  readonly runId: string;
  readonly kind: RecoveryKind;
  readonly parentGeneration: string | null;
}

let generationCounter = 0;

function nextGenerationId(): string {
  generationCounter += 1;
  return `GEN-${String(generationCounter).padStart(4, '0')}`;
}

/**
 * Append a recovery generation to the lineage.
 *
 * The appended generation is frozen (immutable). The lineage array is mutated by
 * appending; the generation object itself can never change.
 */
export function appendGeneration(
  lineage: RecoveryGeneration[],
  input: RecoveryGenerationInput,
): RecoveryGeneration {
  const generation: RecoveryGeneration = Object.freeze({
    id: nextGenerationId(),
    runId: input.runId,
    kind: input.kind,
    parentGeneration: input.parentGeneration,
  });
  lineage.push(generation);
  return generation;
}

/**
 * Navigate the lineage from a generation back to its root.
 *
 * Returns the ordered path [root ... target]. Throws if:
 *  - the target id is not in the lineage;
 *  - the parent chain is broken (a non-null parent that is absent);
 *  - a cycle is detected (multi-node A->B->A or self-referential parent).
 *
 * Cycles indicate corrupted historical data: lineages are append-only and
 * immutable, so a cycle can never be legitimate. FAIL CLOSED by throwing —
 * never return a partial path or [].
 */
export function navigateLineage(
  lineage: readonly RecoveryGeneration[],
  targetId: string,
): readonly RecoveryGeneration[] {
  const byId = new Map(lineage.map((g) => [g.id, g]));
  const target = byId.get(targetId);
  if (!target) {
    throw new Error(`generation ${targetId} not in lineage`);
  }
  const path: RecoveryGeneration[] = [];
  const visited = new Set<string>();
  let current: RecoveryGeneration | undefined = target;
  while (current) {
    if (visited.has(current.id)) {
      throw new Error(`cycle detected at generation ${current.id} — corrupted lineage`);
    }
    visited.add(current.id);
    path.unshift(current);
    if (current.parentGeneration === null) break;
    const parentId = current.parentGeneration;
    current = byId.get(parentId);
    if (!current) {
      throw new Error(`broken parent chain at ${parentId}`);
    }
  }
  return path;
}

/** The recovery lineage is read-only data; it grants no effect capability. */
export interface RecoveryCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const RECOVERY_CAPABILITIES: RecoveryCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
