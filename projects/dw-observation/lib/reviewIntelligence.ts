// M4 — review intelligence derived from immutable projection history.
//
// Analytics are a PURE READ over the same ordered projection events M0/M2/M3
// already produce. This module creates NO governance authority: every metric is
// a derivation, and every aggregate carries the exact event/evidence references
// it was computed from, so a reviewer can always trace a number back to source.
//
// Hard rules (mirrored from the M0/M2/M3 contracts):
//   * Never invent a value. Missing/unknown inputs stay explicitly UNKNOWN and
//     are reported via `incomplete` markers — never silently defaulted to 0.
//   * Never infer authority, gate outcome, or completion that the source stream
//     does not record.
//   * Compare-runs WARNS when reducer/schema versions are incompatible instead
//     of producing a misleading side-by-side.
//   * No mutation, no network, no credential.

import type { ProjectionEvent } from "@/lib/live";
import { reduceEvents, stableStringify, UNKNOWN } from "@/lib/replay";

/** Identity of the derivation logic itself, so metrics are reproducible. */
export const REDUCER_VERSION = "m4-review-intelligence/1";
export const SCHEMA_VERSION = "1";

export type Confidence = "EXACT" | "PARTIAL" | "UNKNOWN";

/** Why a metric could not be computed exactly. Explicit, never hidden. */
export type IncompleteReason =
  | "NO_EVENTS"
  | "MISSING_TIMESTAMP"
  | "MISSING_SEQUENCE"
  | "UNTERMINATED"
  | "NO_MATCHING_EVENTS"
  | "ANOMALIES_PRESENT";

export interface TraceRef {
  sourceSystem: string;
  sourceEventId: string;
  sequence: number | null;
  occurredAt: string | null;
  eventType: string;
  evidenceRefs: string[];
  authorityRef: string | null;
}

/**
 * A metric plus the exact refs it was derived from.
 *
 * `value === null` means NOT COMPUTABLE from the source — it never means zero.
 */
export interface Metric<T> {
  key: string;
  value: T | null;
  unit: string;
  confidence: Confidence;
  incomplete: IncompleteReason[];
  trace: TraceRef[];
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" && v.length > 0 ? v : fallback;
}

function eventType(e: ProjectionEvent): string {
  return str((e as Record<string, unknown>).event_type, UNKNOWN);
}

function occurredAt(e: ProjectionEvent): string | null {
  return typeof e.occurred_at === "string" && e.occurred_at.length > 0 ? e.occurred_at : null;
}

function seqOf(e: ProjectionEvent): number | null {
  return typeof e.sequence === "number" ? e.sequence : null;
}

function evidenceOf(e: ProjectionEvent): string[] {
  const raw = (e as Record<string, unknown>).evidence_refs;
  if (!Array.isArray(raw)) return [];
  return raw.map((r) => (typeof r === "string" ? r : stableStringify(r)));
}

/** Build a trace reference for one event (the reviewer's back-pointer). */
export function traceOf(e: ProjectionEvent): TraceRef {
  return {
    sourceSystem: str(e.source_system, UNKNOWN),
    sourceEventId: str(e.source_event_id, UNKNOWN),
    sequence: seqOf(e),
    occurredAt: occurredAt(e),
    eventType: eventType(e),
    evidenceRefs: evidenceOf(e),
    authorityRef: str((e as Record<string, unknown>).authority_ref) || null,
  };
}

/** Parse an ISO-8601 instant. Returns null when absent or unparseable. */
function instant(value: string | null): number | null {
  if (value === null) return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

function metric<T>(
  key: string,
  value: T | null,
  unit: string,
  trace: TraceRef[],
  incomplete: IncompleteReason[] = []
): Metric<T> {
  let confidence: Confidence;
  if (value === null) confidence = "UNKNOWN";
  else if (incomplete.length > 0) confidence = "PARTIAL";
  else confidence = "EXACT";
  return { key, value, unit, confidence, incomplete, trace };
}

// ---------------------------------------------------------------------------
// Duration / wait
// ---------------------------------------------------------------------------

export interface DurationBreakdown {
  totalMs: number | null;
  firstEventAt: string | null;
  lastEventAt: string | null;
  terminated: boolean;
}

/**
 * Wall-clock span of the run, derived ONLY from recorded timestamps.
 *
 * A run without a terminal event is reported as UNTERMINATED (elapsed-so-far),
 * not silently presented as a completed duration.
 */
export function runDuration(events: ProjectionEvent[]): Metric<DurationBreakdown> {
  if (events.length === 0) {
    return metric<DurationBreakdown>("run.duration", null, "ms", [], ["NO_EVENTS"]);
  }
  const timed = events.filter((e) => instant(occurredAt(e)) !== null);
  const incomplete: IncompleteReason[] = [];
  if (timed.length < events.length) incomplete.push("MISSING_TIMESTAMP");
  if (timed.length === 0) {
    return metric<DurationBreakdown>("run.duration", null, "ms", events.map(traceOf), [
      "MISSING_TIMESTAMP",
    ]);
  }

  const first = timed[0];
  const last = timed[timed.length - 1];
  const startMs = instant(occurredAt(first));
  const endMs = instant(occurredAt(last));
  const terminated = events.some((e) =>
    ["run_completed", "run_failed", "run_aborted"].includes(eventType(e))
  );
  if (!terminated) incomplete.push("UNTERMINATED");

  return metric(
    "run.duration",
    {
      totalMs: startMs !== null && endMs !== null ? endMs - startMs : null,
      firstEventAt: occurredAt(first),
      lastEventAt: occurredAt(last),
      terminated,
    },
    "ms",
    [traceOf(first), traceOf(last)],
    incomplete
  );
}

export interface GapSpan {
  fromEventId: string;
  toEventId: string;
  ms: number;
}

/** The longest quiet interval between consecutive recorded events. */
export function longestWait(events: ProjectionEvent[]): Metric<GapSpan> {
  const timed = events.filter((e) => instant(occurredAt(e)) !== null);
  if (timed.length < 2) {
    return metric<GapSpan>("run.longest_wait", null, "ms", timed.map(traceOf), [
      timed.length === 0 ? "NO_EVENTS" : "NO_MATCHING_EVENTS",
    ]);
  }
  const incomplete: IncompleteReason[] =
    timed.length < events.length ? ["MISSING_TIMESTAMP"] : [];

  let best: GapSpan | null = null;
  let bestPair: [ProjectionEvent, ProjectionEvent] | null = null;
  for (let i = 1; i < timed.length; i++) {
    const prev = timed[i - 1];
    const cur = timed[i];
    const a = instant(occurredAt(prev));
    const b = instant(occurredAt(cur));
    if (a === null || b === null) continue;
    const ms = b - a;
    if (best === null || ms > best.ms) {
      best = {
        fromEventId: str(prev.source_event_id, UNKNOWN),
        toEventId: str(cur.source_event_id, UNKNOWN),
        ms,
      };
      bestPair = [prev, cur];
    }
  }
  return metric(
    "run.longest_wait",
    best,
    "ms",
    bestPair ? bestPair.map(traceOf) : [],
    incomplete
  );
}

// ---------------------------------------------------------------------------
// Retry / recovery
// ---------------------------------------------------------------------------

export interface RetryStat {
  key: string;
  attempts: number;
  eventIds: string[];
}

/**
 * Repeated attempts on the same node/gate, derived from recorded events only.
 *
 * "Attempts" counts recorded transition events per target; it does NOT infer an
 * unrecorded retry.
 */
export function retryProfile(events: ProjectionEvent[]): Metric<RetryStat[]> {
  const buckets = new Map<string, ProjectionEvent[]>();
  for (const e of events) {
    const type = eventType(e);
    const gate = str((e as Record<string, unknown>).gate);
    const node = str((e as Record<string, unknown>).node_id);
    let key: string | null = null;
    if (type.startsWith("gate_") && gate.length > 0) key = `gate:${gate}`;
    else if (type.startsWith("node_") && node.length > 0) key = `node:${node}`;
    if (key === null) continue;
    const list = buckets.get(key) ?? [];
    list.push(e);
    buckets.set(key, list);
  }

  if (buckets.size === 0) {
    return metric<RetryStat[]>("run.retries", null, "attempts", [], ["NO_MATCHING_EVENTS"]);
  }

  const stats: RetryStat[] = [];
  const trace: TraceRef[] = [];
  for (const [key, list] of Array.from(buckets.entries()).sort((a, b) =>
    a[0].localeCompare(b[0])
  )) {
    if (list.length > 1) {
      stats.push({
        key,
        attempts: list.length,
        eventIds: list.map((e) => str(e.source_event_id, UNKNOWN)),
      });
      for (const e of list) trace.push(traceOf(e));
    }
  }
  return metric("run.retries", stats, "attempts", trace);
}

export interface RecoverySpan {
  failureEventId: string;
  recoveryEventId: string | null;
  target: string;
  ms: number | null;
  recovered: boolean;
}

/**
 * Failure -> recovery spans. An unrecovered failure is reported with
 * `recovered: false` and `ms: null` — never as a zero-duration recovery.
 */
export function recoveryProfile(events: ProjectionEvent[]): Metric<RecoverySpan[]> {
  const FAILURE = new Set(["gate_failed", "node_failed", "run_failed"]);
  const RECOVERY = new Set([
    "gate_passed",
    "gate_approved",
    "gate_released",
    "node_completed",
    "node_started",
    "node_progress",
  ]);

  const spans: RecoverySpan[] = [];
  const trace: TraceRef[] = [];
  const incomplete: IncompleteReason[] = [];

  events.forEach((e, idx) => {
    if (!FAILURE.has(eventType(e))) return;
    const gate = str((e as Record<string, unknown>).gate);
    const node = str((e as Record<string, unknown>).node_id);
    const target = gate.length > 0 ? `gate:${gate}` : node.length > 0 ? `node:${node}` : "run";

    let recovery: ProjectionEvent | null = null;
    for (let j = idx + 1; j < events.length; j++) {
      const c = events[j];
      if (!RECOVERY.has(eventType(c))) continue;
      const cGate = str((c as Record<string, unknown>).gate);
      const cNode = str((c as Record<string, unknown>).node_id);
      const cTarget =
        cGate.length > 0 ? `gate:${cGate}` : cNode.length > 0 ? `node:${cNode}` : "run";
      if (cTarget === target) {
        recovery = c;
        break;
      }
    }

    const a = instant(occurredAt(e));
    const b = recovery ? instant(occurredAt(recovery)) : null;
    if (recovery !== null && (a === null || b === null)) {
      incomplete.push("MISSING_TIMESTAMP");
    }
    spans.push({
      failureEventId: str(e.source_event_id, UNKNOWN),
      recoveryEventId: recovery ? str(recovery.source_event_id, UNKNOWN) : null,
      target,
      ms: a !== null && b !== null ? b - a : null,
      recovered: recovery !== null,
    });
    trace.push(traceOf(e));
    if (recovery) trace.push(traceOf(recovery));
  });

  if (spans.length === 0) {
    return metric<RecoverySpan[]>("run.recoveries", null, "ms", [], ["NO_MATCHING_EVENTS"]);
  }
  return metric("run.recoveries", spans, "ms", trace, incomplete);
}

// ---------------------------------------------------------------------------
// Handoff
// ---------------------------------------------------------------------------

export interface HandoffSpan {
  fromActor: string;
  toActor: string;
  atEventId: string;
  ms: number | null;
}

function actorKey(e: ProjectionEvent): string {
  const raw = (e as Record<string, unknown>).actor;
  if (typeof raw === "string" && raw.length > 0) return raw;
  if (raw && typeof raw === "object") {
    const a = raw as Record<string, unknown>;
    const parts = [str(a.kind), str(a.id)].filter((x) => x.length > 0);
    if (parts.length > 0) return parts.join(":");
  }
  return UNKNOWN;
}

/**
 * Actor-to-actor handoffs derived from recorded actors.
 *
 * Transitions into or out of an UNKNOWN actor are NOT reported as handoffs —
 * that would fabricate a participant the source never named.
 */
export function handoffProfile(events: ProjectionEvent[]): Metric<HandoffSpan[]> {
  const known = events.filter((e) => actorKey(e) !== UNKNOWN);
  if (known.length === 0) {
    return metric<HandoffSpan[]>("run.handoffs", null, "count", [], ["NO_MATCHING_EVENTS"]);
  }
  const incomplete: IncompleteReason[] =
    known.length < events.length ? ["NO_MATCHING_EVENTS"] : [];

  const spans: HandoffSpan[] = [];
  const trace: TraceRef[] = [];
  for (let i = 1; i < known.length; i++) {
    const prev = known[i - 1];
    const cur = known[i];
    const from = actorKey(prev);
    const to = actorKey(cur);
    if (from === to) continue;
    const a = instant(occurredAt(prev));
    const b = instant(occurredAt(cur));
    if (a === null || b === null) incomplete.push("MISSING_TIMESTAMP");
    spans.push({
      fromActor: from,
      toActor: to,
      atEventId: str(cur.source_event_id, UNKNOWN),
      ms: a !== null && b !== null ? b - a : null,
    });
    trace.push(traceOf(prev), traceOf(cur));
  }
  return metric("run.handoffs", spans, "count", trace, incomplete);
}

// ---------------------------------------------------------------------------
// Full report
// ---------------------------------------------------------------------------

export interface ReviewReport {
  runId: string;
  reducerVersion: string;
  schemaVersion: string;
  eventCount: number;
  /** Anomalies inherited from the reducer — surfaced, never suppressed. */
  anomalyCount: number;
  historyComplete: boolean;
  incompleteMarkers: IncompleteReason[];
  duration: Metric<DurationBreakdown>;
  longestWait: Metric<GapSpan>;
  retries: Metric<RetryStat[]>;
  recoveries: Metric<RecoverySpan[]>;
  handoffs: Metric<HandoffSpan[]>;
  /** Authority is only ever REPORTED from source, never derived. */
  createsAuthority: false;
}

/** Derive the full read-only review report for one run. */
export function reviewRun(runId: string, events: ProjectionEvent[]): ReviewReport {
  const projection = reduceEvents(events);
  const duration = runDuration(events);
  const longest = longestWait(events);
  const retries = retryProfile(events);
  const recoveries = recoveryProfile(events);
  const handoffs = handoffProfile(events);

  const markers = new Set<IncompleteReason>();
  for (const m of [duration, longest, retries, recoveries, handoffs]) {
    for (const r of m.incomplete) markers.add(r);
  }
  if (projection.anomalies.length > 0) markers.add("ANOMALIES_PRESENT");
  if (events.length === 0) markers.add("NO_EVENTS");

  return {
    runId,
    reducerVersion: REDUCER_VERSION,
    schemaVersion: SCHEMA_VERSION,
    eventCount: events.length,
    anomalyCount: projection.anomalies.length,
    historyComplete: markers.size === 0,
    incompleteMarkers: Array.from(markers).sort(),
    duration,
    longestWait: longest,
    retries,
    recoveries,
    handoffs,
    createsAuthority: false,
  };
}

// ---------------------------------------------------------------------------
// Compare runs (version-aware)
// ---------------------------------------------------------------------------

export type CompareWarning =
  | "REDUCER_VERSION_MISMATCH"
  | "SCHEMA_VERSION_MISMATCH"
  | "INCOMPLETE_HISTORY"
  | "ANOMALIES_PRESENT";

export interface RunComparison {
  left: ReviewReport;
  right: ReviewReport;
  comparable: boolean;
  warnings: CompareWarning[];
  deltas: Record<string, number | null>;
}

/**
 * Side-by-side comparison that WARNS instead of misleading.
 *
 * Incompatible reducer/schema versions set `comparable: false` and suppress the
 * numeric deltas — a reviewer is never shown a diff computed across two
 * different derivation contracts.
 */
export function compareRuns(left: ReviewReport, right: ReviewReport): RunComparison {
  const warnings: CompareWarning[] = [];
  if (left.reducerVersion !== right.reducerVersion) warnings.push("REDUCER_VERSION_MISMATCH");
  if (left.schemaVersion !== right.schemaVersion) warnings.push("SCHEMA_VERSION_MISMATCH");
  if (!left.historyComplete || !right.historyComplete) warnings.push("INCOMPLETE_HISTORY");
  if (left.anomalyCount > 0 || right.anomalyCount > 0) warnings.push("ANOMALIES_PRESENT");

  const versionIncompatible =
    warnings.includes("REDUCER_VERSION_MISMATCH") ||
    warnings.includes("SCHEMA_VERSION_MISMATCH");

  const deltas: Record<string, number | null> = {};
  if (!versionIncompatible) {
    const lDur = left.duration.value?.totalMs ?? null;
    const rDur = right.duration.value?.totalMs ?? null;
    deltas["duration.totalMs"] = lDur !== null && rDur !== null ? rDur - lDur : null;

    const lWait = left.longestWait.value?.ms ?? null;
    const rWait = right.longestWait.value?.ms ?? null;
    deltas["longestWait.ms"] = lWait !== null && rWait !== null ? rWait - lWait : null;

    const countAttempts = (r: ReviewReport) =>
      r.retries.value === null
        ? null
        : r.retries.value.reduce((acc, s) => acc + s.attempts, 0);
    const lRetry = countAttempts(left);
    const rRetry = countAttempts(right);
    deltas["retries.attempts"] = lRetry !== null && rRetry !== null ? rRetry - lRetry : null;

    const lHand = left.handoffs.value?.length ?? null;
    const rHand = right.handoffs.value?.length ?? null;
    deltas["handoffs.count"] = lHand !== null && rHand !== null ? rHand - lHand : null;

    deltas["eventCount"] = right.eventCount - left.eventCount;
    deltas["anomalyCount"] = right.anomalyCount - left.anomalyCount;
  }

  return { left, right, comparable: !versionIncompatible, warnings, deltas };
}
