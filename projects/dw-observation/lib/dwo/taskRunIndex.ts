/**
 * R2-F — TaskRunIndexV2: authoritative Task → Root-run relation index.
 *
 * A Task does not "obviously" own a run. The relation is a FACT that must be
 * carried by an explicit, versioned, digest-pinned record. Nothing here is
 * derived from a run id, a display name, a Jira-like key, a branch name, or
 * any string pattern — those correlations are coincidences that break the
 * moment someone names a branch after a task they are not working on.
 *
 * Consequently there is deliberately no `inferTaskRefFromRunId(...)`. The only
 * way to obtain a taskRef is to read it from a relation record.
 *
 * Two further facts the index must carry, because both are routinely faked by
 * convenience code:
 *
 *   - SUPERSESSION. A relation record may be replaced. Which record is live is
 *     decided by an explicit supersession chain, never by "the newest one".
 *   - UNIQUENESS. Two records claiming different root sets for the same task
 *     at the same relation revision is a CONFLICT, not a merge. Failing open
 *     here would silently drop or duplicate a run's ownership.
 *
 * Read-only. Grants no effect capability.
 */

/** One authoritative Task → Root-run relation record. */
export interface TaskRunRelationRecord {
  /** The task this relation is about. Read from the record, never inferred. */
  readonly taskRef: string;
  /** Revision of the relation itself — the conflict-detection key. */
  readonly relationRevisionId: string;
  /** Root runs this task owns at this revision. */
  readonly rootRunIds: readonly string[];
  /** Which system asserted the relation (Jira, DWO, manual, ...). */
  readonly sourceSystem: string;
  /** The record id in that source system. */
  readonly sourceRecordId: string;
  /** Digest pinning the source record's content. */
  readonly sourceDigest: string;
  /** Durable position of this relation record. */
  readonly durablePosition: number;
  /** The relation revision this record replaces, if any. */
  readonly supersedesRevisionId: string | null;
}

/** Reason codes for an unresolved or rejected relation lookup. */
export type RelationReason =
  | 'RELATION_RESOLVED'
  | 'RELATION_CONFLICT'
  | 'MISSING_TASK_REF'
  | 'MISSING_RELATION_REVISION'
  | 'MISSING_SOURCE_IDENTITY'
  | 'MISSING_SOURCE_DIGEST'
  | 'MISSING_ROOT_RUN_ID'
  | 'NEGATIVE_DURABLE_POSITION'
  | 'SUPERSEDED_REVISION'
  | 'SUPERSESSION_CYCLE'
  | 'UNKNOWN_UNRESOLVED';

/** The read-only relation decision. */
export interface RelationDecision {
  readonly status: 'RESOLVED' | 'UNKNOWN_UNRESOLVED';
  readonly reason: RelationReason;
  readonly taskRef: string;
  readonly relationRevisionId: string | null;
  readonly rootRunIds: readonly string[];
  /** All revisions that disagreed, when reason === RELATION_CONFLICT. */
  readonly conflictingRevisions: readonly string[];
}

const UNRESOLVED = 'UNKNOWN';

function isEstablished(value: string | 'UNKNOWN'): value is string {
  return typeof value === 'string' && value.length > 0 && value !== UNRESOLVED;
}

/**
 * Validate a single relation record's internal coherence.
 *
 * Returns the offending field names; empty means the record is well-formed.
 * This is deliberately separate from the cross-record checks so a malformed
 * record is reported as malformed rather than as a conflict.
 */
function validateRecord(record: TaskRunRelationRecord): string[] {
  const bad: string[] = [];
  if (!isEstablished(record.taskRef)) bad.push('taskRef');
  if (!isEstablished(record.relationRevisionId)) bad.push('relationRevisionId');
  if (!isEstablished(record.sourceSystem)) bad.push('sourceSystem');
  if (!isEstablished(record.sourceRecordId)) bad.push('sourceRecordId');
  if (!isEstablished(record.sourceDigest)) bad.push('sourceDigest');
  if (!Number.isInteger(record.durablePosition) || record.durablePosition < 0) {
    bad.push('durablePosition');
  }
  if (record.rootRunIds.length === 0) {
    // A relation that owns nothing is not a relation.
    bad.push('rootRunIds');
  }
  for (const r of record.rootRunIds) {
    if (!isEstablished(r)) bad.push(`rootRunId:${r || '<empty>'}`);
  }
  return bad;
}

/**
 * Resolve the authoritative root runs for a task.
 *
 * `records` must be the FULL set of relation records for the task — the caller
 * is expected to have selected them by taskRef from an authoritative source,
 * never by pattern-matching run ids.
 *
 * Resolution order:
 *   1. validate every record; a malformed record is unresolved;
 *   2. drop records explicitly superseded by another record in the set;
 *   3. detect supersession cycles among the survivors;
 *   4. any surviving disagreement about the root set at a single relation
 *      revision is RELATION_CONFLICT — never a merge, never "newest wins";
 *   5. exactly one surviving root set → RESOLVED.
 *
 * The supersession chain is walked rather than inferred from durablePosition,
 * because "newest" and "live" are different claims.
 */
export function resolveTaskRootRuns(
  taskRef: string,
  records: readonly TaskRunRelationRecord[],
): RelationDecision {
  const unresolved = (reason: RelationReason, bad: readonly string[] = []): RelationDecision => ({
    status: 'UNKNOWN_UNRESOLVED',
    reason,
    taskRef,
    relationRevisionId: null,
    rootRunIds: [],
    conflictingRevisions: [],
    ...(bad.length > 0 ? { missingRefs: bad } : {}),
  } as RelationDecision);

  if (!isEstablished(taskRef)) {
    return unresolved('MISSING_TASK_REF');
  }

  const forTask = records.filter((r) => r.taskRef === taskRef);
  if (forTask.length === 0) {
    // No authoritative record ⇒ the relation is unproven. Not "no runs".
    return unresolved('UNKNOWN_UNRESOLVED');
  }

  for (const r of forTask) {
    const bad = validateRecord(r);
    if (bad.length > 0) {
      const reason: RelationReason = bad.includes('taskRef')
        ? 'MISSING_TASK_REF'
        : bad.includes('relationRevisionId')
          ? 'MISSING_RELATION_REVISION'
          : bad.includes('sourceDigest')
            ? 'MISSING_SOURCE_DIGEST'
            : bad.includes('rootRunIds') || bad.some((b) => b.startsWith('rootRunId:'))
              ? 'MISSING_ROOT_RUN_ID'
              : bad.includes('durablePosition')
                ? 'NEGATIVE_DURABLE_POSITION'
                : 'MISSING_SOURCE_IDENTITY';
      return unresolved(reason, bad);
    }
  }

  // Supersession must form a chain, not a cycle. This is checked over the FULL
  // record set before any liveness filtering: a mutual-supersession pair marks
  // both revisions as superseded, so filtering first would report "nothing
  // live" and hide the incoherent lineage behind it.
  const allByRevision = new Map(forTask.map((r) => [r.relationRevisionId, r]));
  for (const start of forTask) {
    const seen = new Set<string>([start.relationRevisionId]);
    let cursor = start;
    while (cursor.supersedesRevisionId !== null && isEstablished(cursor.supersedesRevisionId)) {
      if (seen.has(cursor.supersedesRevisionId)) {
        return unresolved('SUPERSESSION_CYCLE');
      }
      seen.add(cursor.supersedesRevisionId);
      const next = allByRevision.get(cursor.supersedesRevisionId);
      if (!next) break; // chain leaves this task's set — nothing more to walk
      cursor = next;
    }
  }

  // Drop explicitly superseded records. Supersession is declared, never assumed
  // from recency.
  const supersededRevisions = new Set<string>();
  for (const r of forTask) {
    if (r.supersedesRevisionId !== null && isEstablished(r.supersedesRevisionId)) {
      supersededRevisions.add(r.supersedesRevisionId);
    }
  }
  const live = forTask.filter((r) => !supersededRevisions.has(r.relationRevisionId));

  if (live.length === 0) {
    return unresolved('SUPERSEDED_REVISION');
  }

  // Group survivors by relation revision, then require that every record at a
  // given revision states the SAME root set. Unioning them would silently
  // merge two disagreeing claims into a plausible-looking answer; picking one
  // would silently drop a run. Both are fabrications, so disagreement is a
  // conflict.
  const groups = new Map<string, TaskRunRelationRecord[]>();
  for (const r of live) {
    const key = r.relationRevisionId;
    const bucket = groups.get(key) ?? [];
    bucket.push(r);
    groups.set(key, bucket);
  }

  const disagreements: string[] = [];
  for (const [, bucket] of groups) {
    const canonical = [...bucket[0].rootRunIds].sort().join(' ');
    for (const other of bucket.slice(1)) {
      if ([...other.rootRunIds].sort().join(' ') !== canonical) {
        disagreements.push(bucket[0].relationRevisionId);
        break;
      }
    }
  }

  if (groups.size > 1 || disagreements.length > 0) {
    return {
      status: 'UNKNOWN_UNRESOLVED',
      reason: 'RELATION_CONFLICT',
      taskRef,
      relationRevisionId: null,
      rootRunIds: [],
      conflictingRevisions: [...groups.keys()].sort(),
    };
  }

  const [[revisionId, bucket]] = [...groups.entries()];
  return {
    status: 'RESOLVED',
    reason: 'RELATION_RESOLVED',
    taskRef,
    relationRevisionId: revisionId,
    rootRunIds: [...new Set(bucket.flatMap((r) => [...r.rootRunIds]))].sort(),
    conflictingRevisions: [],
  };
}

/**
 * Index a set of relation records by taskRef for lookup.
 *
 * The index stores what the records SAY. It performs no inference: a task with
 * no record simply has no entry, which callers must treat as unproven.
 */
export function buildTaskRunIndexV2(
  records: readonly TaskRunRelationRecord[],
): ReadonlyMap<string, readonly TaskRunRelationRecord[]> {
  const index = new Map<string, TaskRunRelationRecord[]>();
  for (const r of records) {
    const bucket = index.get(r.taskRef) ?? [];
    bucket.push(r);
    index.set(r.taskRef, bucket);
  }
  return index;
}

/**
 * Look a task up in a built index and resolve it.
 *
 * This is the intended entry point: select by declared taskRef, then resolve.
 * There is intentionally no reverse lookup "which task owns this run?" —
 * answering that would require exactly the pattern inference this module
 * refuses to perform.
 */
export function resolveFromIndex(
  index: ReadonlyMap<string, readonly TaskRunRelationRecord[]>,
  taskRef: string,
): RelationDecision {
  return resolveTaskRootRuns(taskRef, index.get(taskRef) ?? []);
}

/** The relation index is read-only; it grants no effect capability. */
export interface TaskRunIndexCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const TASK_RUN_INDEX_CAPABILITIES: TaskRunIndexCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
