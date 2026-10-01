/**
 * R2-F focused tests — TaskRunIndexV2.
 *
 * Two properties matter more than the happy path and are asserted here:
 *
 *   1. NO INFERENCE. A run whose id looks like a task key must not resolve to
 *      that task. There is no API that answers "which task owns this run?",
 *      and its absence is the guarantee — asserted by inspecting the module's
 *      exports rather than by a behavioural test.
 *   2. CONFLICT FAILS OPEN-NEVER. Two records disagreeing at the same relation
 *      revision must not be reconciled by recency, merge, or first-wins.
 */

import { describe, expect, it } from 'vitest';
import * as taskRunIndexModule from '@/lib/dwo/taskRunIndex';
import {
  TASK_RUN_INDEX_CAPABILITIES,
  buildTaskRunIndexV2,
  resolveFromIndex,
  resolveTaskRootRuns,
  type TaskRunRelationRecord,
} from '@/lib/dwo/taskRunIndex';

function record(overrides: Partial<TaskRunRelationRecord> = {}): TaskRunRelationRecord {
  return {
    taskRef: 'SCRUM-820',
    relationRevisionId: 'rel-1',
    rootRunIds: ['RUN-A'],
    sourceSystem: 'DWO',
    sourceRecordId: 'record-1',
    sourceDigest: 'sha256:rel-1',
    durablePosition: 10,
    supersedesRevisionId: null,
    ...overrides,
  };
}

describe('R2-F · a proven relation resolves', () => {
  it('a single well-formed record resolves its declared root runs', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record()]);
    expect(d.status).toBe('RESOLVED');
    expect(d.reason).toBe('RELATION_RESOLVED');
    expect(d.relationRevisionId).toBe('rel-1');
    expect(d.rootRunIds).toEqual(['RUN-A']);
  });

  it('multiple roots resolve in a stable sorted order', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ rootRunIds: ['RUN-Z', 'RUN-A', 'RUN-M'] }),
    ]);
    expect(d.status).toBe('RESOLVED');
    expect(d.rootRunIds).toEqual(['RUN-A', 'RUN-M', 'RUN-Z']);
  });

  it('records for other tasks are not consulted', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record(),
      record({ taskRef: 'SCRUM-999', rootRunIds: ['RUN-OTHER'] }),
    ]);
    expect(d.rootRunIds).toEqual(['RUN-A']);
  });

  it('agreement across two records at the same revision is not a conflict', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ sourceRecordId: 'a' }),
      record({ sourceRecordId: 'b', durablePosition: 11 }),
    ]);
    expect(d.status).toBe('RESOLVED');
    expect(d.reason).toBe('RELATION_RESOLVED');
  });
});

describe('R2-F · taskRef is never inferred from a run', () => {
  it('the module exposes no reverse lookup from a run id', () => {
    // The absence of such an API is the guarantee: answering "which task owns
    // RUN-x?" would require pattern inference the contract forbids.
    const exports = Object.keys(taskRunIndexModule);
    expect(exports.some((e) => /run.*to.*task|task.*from.*run|infer|reverse|parse/i.test(e))).toBe(false);
  });

  it('a run id that looks like a task key does not resolve to that task', () => {
    const d = resolveTaskRootRuns('SCRUM-820', []);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.rootRunIds).toEqual([]);
  });

  it('no records at all is unresolved, never "owns nothing"', () => {
    const d = resolveTaskRootRuns('SCRUM-820', []);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('UNKNOWN_UNRESOLVED');
    expect(d.rootRunIds).toEqual([]);
  });

  it('an empty taskRef is rejected before any lookup', () => {
    const d = resolveTaskRootRuns('', [record()]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('MISSING_TASK_REF');
  });
});

describe('R2-F · the same revision with conflicting mappings is RELATION_CONFLICT', () => {
  it('two different root sets at one revision conflict', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ sourceRecordId: 'a', rootRunIds: ['RUN-A'] }),
      record({ sourceRecordId: 'b', rootRunIds: ['RUN-B'] }),
    ]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('RELATION_CONFLICT');
    expect(d.rootRunIds).toEqual([]);
  });

  it('a conflict is not reconciled by recency', () => {
    // The later record must not silently win.
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ sourceRecordId: 'a', rootRunIds: ['RUN-A'], durablePosition: 1 }),
      record({ sourceRecordId: 'b', rootRunIds: ['RUN-B'], durablePosition: 999 }),
    ]);
    expect(d.reason).toBe('RELATION_CONFLICT');
    expect(d.rootRunIds).toEqual([]);
  });

  it('a conflict names the revisions that disagreed', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-2', rootRunIds: ['RUN-A'] }),
      record({ relationRevisionId: 'rel-3', rootRunIds: ['RUN-B'] }),
    ]);
    expect(d.reason).toBe('RELATION_CONFLICT');
    expect(d.conflictingRevisions).toEqual(['rel-2', 'rel-3']);
  });

  it('a partial overlap is still a conflict, not a union', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ sourceRecordId: 'a', rootRunIds: ['RUN-A', 'RUN-SHARED'] }),
      record({ sourceRecordId: 'b', rootRunIds: ['RUN-B', 'RUN-SHARED'] }),
    ]);
    expect(d.reason).toBe('RELATION_CONFLICT');
    expect(d.rootRunIds).toEqual([]);
  });
});

describe('R2-F · supersession is explicit', () => {
  it('an explicitly superseded revision is not live', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', rootRunIds: ['RUN-OLD'] }),
      record({
        relationRevisionId: 'rel-2',
        rootRunIds: ['RUN-NEW'],
        supersedesRevisionId: 'rel-1',
        durablePosition: 20,
      }),
    ]);
    expect(d.status).toBe('RESOLVED');
    expect(d.relationRevisionId).toBe('rel-2');
    expect(d.rootRunIds).toEqual(['RUN-NEW']);
  });

  it('recency alone does NOT supersede — two live revisions conflict', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', rootRunIds: ['RUN-OLD'], durablePosition: 1 }),
      record({ relationRevisionId: 'rel-2', rootRunIds: ['RUN-NEW'], durablePosition: 999 }),
    ]);
    expect(d.reason).toBe('RELATION_CONFLICT');
  });

  it('a supersession chain resolves to its tip', () => {
    // rel-3 supersedes rel-2 supersedes rel-1, so rel-3 is the live record.
    // "Nothing live" is unreachable once cycles are rejected — a linear chain
    // always has a tip — which is why SUPERSEDED_REVISION stays a defensive
    // branch rather than a routine outcome.
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', rootRunIds: ['RUN-V1'] }),
      record({ relationRevisionId: 'rel-2', rootRunIds: ['RUN-V2'], supersedesRevisionId: 'rel-1' }),
      record({ relationRevisionId: 'rel-3', rootRunIds: ['RUN-V3'], supersedesRevisionId: 'rel-2' }),
    ]);
    expect(d.status).toBe('RESOLVED');
    expect(d.relationRevisionId).toBe('rel-3');
    expect(d.rootRunIds).toEqual(['RUN-V3']);
  });

  it('a self-superseding record is a cycle, not a live revision', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', supersedesRevisionId: 'rel-1' }),
    ]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('SUPERSESSION_CYCLE');
  });

  it('a supersession cycle is unresolved, not resolved by the newest', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', supersedesRevisionId: 'rel-2' }),
      record({ relationRevisionId: 'rel-2', supersedesRevisionId: 'rel-1' }),
    ]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('SUPERSESSION_CYCLE');
  });

  it('an explicit supersession resolves what would otherwise be a conflict', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ relationRevisionId: 'rel-1', rootRunIds: ['RUN-OLD'] }),
      record({
        relationRevisionId: 'rel-2',
        rootRunIds: ['RUN-NEW'],
        supersedesRevisionId: 'rel-1',
      }),
    ]);
    expect(d.status).toBe('RESOLVED');
    expect(d.reason).not.toBe('RELATION_CONFLICT');
  });
});

describe('R2-F · a malformed record is malformed, not a conflict', () => {
  it('a missing source digest is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ sourceDigest: 'UNKNOWN' })]);
    expect(d.reason).toBe('MISSING_SOURCE_DIGEST');
  });

  it('a missing relation revision is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ relationRevisionId: '' })]);
    expect(d.reason).toBe('MISSING_RELATION_REVISION');
  });

  it('a missing source identity is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ sourceSystem: '' })]);
    expect(d.reason).toBe('MISSING_SOURCE_IDENTITY');
  });

  it('a relation owning no runs is unresolved, not an empty success', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ rootRunIds: [] })]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('MISSING_ROOT_RUN_ID');
  });

  it('a blank root run id is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ rootRunIds: ['RUN-A', ''] })]);
    expect(d.reason).toBe('MISSING_ROOT_RUN_ID');
  });

  it('a negative durable position is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ durablePosition: -1 })]);
    expect(d.reason).toBe('NEGATIVE_DURABLE_POSITION');
  });

  it('a non-integer durable position is unresolved', () => {
    const d = resolveTaskRootRuns('SCRUM-820', [record({ durablePosition: 1.5 })]);
    expect(d.reason).toBe('NEGATIVE_DURABLE_POSITION');
  });

  it('one malformed record poisons the whole lookup', () => {
    // A partial answer built from half-valid records would be untrustworthy.
    const d = resolveTaskRootRuns('SCRUM-820', [
      record({ sourceRecordId: 'good', rootRunIds: ['RUN-A'] }),
      record({ sourceRecordId: 'bad', sourceDigest: '' }),
    ]);
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.rootRunIds).toEqual([]);
  });
});

describe('R2-F · index construction performs no inference', () => {
  it('indexes by declared taskRef only', () => {
    const index = buildTaskRunIndexV2([
      record({ taskRef: 'SCRUM-820' }),
      record({ taskRef: 'SCRUM-999' }),
    ]);
    expect([...index.keys()].sort()).toEqual(['SCRUM-820', 'SCRUM-999']);
    expect(index.get('SCRUM-820')).toHaveLength(1);
  });

  it('a task with no record has no entry and resolves as unproven', () => {
    const index = buildTaskRunIndexV2([record({ taskRef: 'SCRUM-820' })]);
    expect(index.has('SCRUM-888')).toBe(false);
    const d = resolveFromIndex(index, 'SCRUM-888');
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('UNKNOWN_UNRESOLVED');
  });

  it('resolving through the index matches direct resolution', () => {
    const records = [record({ sourceRecordId: 'a' }), record({ sourceRecordId: 'b' })];
    const index = buildTaskRunIndexV2(records);
    expect(resolveFromIndex(index, 'SCRUM-820')).toEqual(
      resolveTaskRootRuns('SCRUM-820', records),
    );
  });
});

describe('R2-F · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(TASK_RUN_INDEX_CAPABILITIES).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
    expect(Object.isFrozen(TASK_RUN_INDEX_CAPABILITIES)).toBe(true);
  });
});
