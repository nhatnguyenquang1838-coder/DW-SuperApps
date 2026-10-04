/**
 * R2-D — Authoritative authority-state vocabulary.
 *
 * Authority is DERIVED from explicit source evidence, never inferred from
 * absence and never defaulted optimistically. The closed vocabulary is:
 *
 *   PENDING | GRANTED | DENIED | EXPIRED | REVOKED | NOT_REQUIRED | UNKNOWN
 *
 * The two failure modes this module exists to prevent:
 *
 *   1. Inferring DENIED from absence. "No approval record was found" is not
 *      the same fact as "an approver said no". Absence is UNKNOWN.
 *   2. Inferring GRANTED from incomplete data. A grant requires source
 *      identity, an explicit scope, and time evidence. Anything less is
 *      UNKNOWN — never GRANTED, and never DENIED either, since a partial
 *      record proves neither.
 *
 * EXPIRED and REVOKED are terminal facts about a grant that DID exist, so
 * they require the same source identity as GRANTED; they are distinct from
 * UNKNOWN because a provably lapsed grant is a known outcome, not an
 * unprovable one.
 *
 * Read-only. Grants no effect capability and mints no authority.
 */

/** The closed authoritative vocabulary. No other value is representable. */
export type AuthorityState =
  | 'PENDING'
  | 'GRANTED'
  | 'DENIED'
  | 'EXPIRED'
  | 'REVOKED'
  | 'NOT_REQUIRED'
  | 'UNKNOWN';

/**
 * The explicit authority evidence record.
 *
 * Every field is required-but-possibly-absent by VALUE: an empty string or
 * 'UNKNOWN' means the fact is not established. The type deliberately does not
 * make these optional, so a caller cannot omit evidence by accident and have
 * the derivation silently treat the omission as a decision.
 */
export interface AuthorityEvidence {
  /** Who/what asserted this state (approver id, policy engine, contract ref). */
  readonly sourceIdentity: string | 'UNKNOWN';
  /** Digest pinning the source record that asserted the state. */
  readonly sourceDigest: string | 'UNKNOWN';
  /** The exact scope the assertion covers (e.g. merge_to_main, deploy). */
  readonly scope: string | 'UNKNOWN';
  /** ISO-8601 instant the assertion was made. */
  readonly assertedAt: string | 'UNKNOWN';
  /** ISO-8601 instant the grant lapses, when the assertion is time-bounded. */
  readonly expiresAt: string | 'UNKNOWN';
  /** The asserted state itself. */
  readonly assertedState: AuthorityState | 'UNKNOWN' | string;
}

/** Reason codes explaining why a derivation did not land on GRANTED. */
export type AuthorityReason =
  | 'AUTHORITY_GRANTED'
  | 'AUTHORITY_DENIED'
  | 'AUTHORITY_EXPIRED'
  | 'AUTHORITY_REVOKED'
  | 'AUTHORITY_PENDING'
  | 'AUTHORITY_NOT_REQUIRED'
  | 'UNKNOWN_NO_ASSERTION'
  | 'UNKNOWN_UNSUPPORTED_STATE'
  | 'UNKNOWN_INCOMPLETE_EVIDENCE'
  | 'UNKNOWN_INVALID_TIME_EVIDENCE'
  | 'UNKNOWN_UNRESOLVED';

/** The read-only derivation result. */
export interface AuthorityDecision {
  readonly state: AuthorityState;
  readonly reason: AuthorityReason;
  /** True only when state === 'GRANTED'. Convenient for gate guards. */
  readonly granted: boolean;
}

/** The closed set of representable states, for runtime validation. */
export const AUTHORITY_STATES: readonly AuthorityState[] = Object.freeze([
  'PENDING',
  'GRANTED',
  'DENIED',
  'EXPIRED',
  'REVOKED',
  'NOT_REQUIRED',
  'UNKNOWN',
]);

/**
 * A state that does not require a grant record at all. NOT_REQUIRED and
 * PENDING describe the ABSENCE of a requirement or of a decision, so they
 * legitimately carry no approver identity.
 */
const NO_SOURCE_REQUIRED_STATES: ReadonlySet<string> = new Set<AuthorityState>([
  'NOT_REQUIRED',
  'PENDING',
]);

const UNKNOWN_TOKEN = 'UNKNOWN';

function isEstablished(value: string | 'UNKNOWN'): value is string {
  return typeof value === 'string' && value.length > 0 && value !== UNKNOWN_TOKEN;
}

/** Parse an ISO-8601 instant to epoch millis, or null when unparseable. */
function parseInstant(value: string | 'UNKNOWN'): number | null {
  if (!isEstablished(value)) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Derive the authoritative authority state from explicit evidence.
 *
 * Fail-closed throughout:
 * - an out-of-vocabulary asserted state is UNKNOWN, never coerced;
 * - a source-backed state without identity+scope+digest is UNKNOWN, never
 *   accepted on partial evidence;
 * - a grant whose expiry is unparseable, or whose asserted time is unparseable,
 *   is UNKNOWN — an unparseable clock cannot prove a grant is still live;
 * - absence of any record is UNKNOWN, never DENIED.
 *
 * `now` is passed in rather than read from the wall clock so the derivation
 * is deterministic and testable. An expired assertion resolves to EXPIRED only
 * when the clock itself is established; otherwise UNKNOWN.
 */
export function deriveAuthorityState(
  evidence: AuthorityEvidence | null | undefined,
  now: string | 'UNKNOWN' = UNKNOWN_TOKEN,
): AuthorityDecision {
  if (!evidence) {
    // No record at all. This is the exact case that must NOT become DENIED.
    return { state: 'UNKNOWN', reason: 'UNKNOWN_NO_ASSERTION', granted: false };
  }

  const asserted = evidence.assertedState;

  // An explicitly asserted UNKNOWN is a real statement about an unresolved
  // state, distinct from having no statement at all. Checked before the
  // "is it established" test, since 'UNKNOWN' is deliberately not established.
  if (asserted === UNKNOWN_TOKEN) {
    return { state: 'UNKNOWN', reason: 'UNKNOWN_UNRESOLVED', granted: false };
  }

  if (!isEstablished(asserted)) {
    return { state: 'UNKNOWN', reason: 'UNKNOWN_NO_ASSERTION', granted: false };
  }

  if (!AUTHORITY_STATES.includes(asserted as AuthorityState)) {
    return { state: 'UNKNOWN', reason: 'UNKNOWN_UNSUPPORTED_STATE', granted: false };
  }

  const assertedState = asserted as AuthorityState;

  if (NO_SOURCE_REQUIRED_STATES.has(assertedState)) {
    // These describe the absence of a requirement/decision, so no approver
    // identity is expected. Scope is still required — an unscoped
    // NOT_REQUIRED is not a statement about anything.
    if (!isEstablished(evidence.scope)) {
      return { state: 'UNKNOWN', reason: 'UNKNOWN_INCOMPLETE_EVIDENCE', granted: false };
    }
    return {
      state: assertedState,
      reason: assertedState === 'NOT_REQUIRED' ? 'AUTHORITY_NOT_REQUIRED' : 'AUTHORITY_PENDING',
      granted: false,
    };
  }

  // GRANTED / DENIED / EXPIRED / REVOKED all describe a real assertion and
  // therefore require a proven source, scope, and digest.
  if (
    !isEstablished(evidence.sourceIdentity) ||
    !isEstablished(evidence.scope) ||
    !isEstablished(evidence.sourceDigest)
  ) {
    // Partial evidence proves neither a grant nor a refusal.
    return { state: 'UNKNOWN', reason: 'UNKNOWN_INCOMPLETE_EVIDENCE', granted: false };
  }

  if (assertedState === 'DENIED') {
    return { state: 'DENIED', reason: 'AUTHORITY_DENIED', granted: false };
  }

  if (assertedState === 'REVOKED') {
    return { state: 'REVOKED', reason: 'AUTHORITY_REVOKED', granted: false };
  }

  // GRANTED and EXPIRED both require usable time evidence: a grant is a claim
  // about a bounded window, and we cannot honor or lapse it on a bad clock.
  const assertedAt = parseInstant(evidence.assertedAt);
  const expiresAt = parseInstant(evidence.expiresAt);
  if (assertedAt === null || expiresAt === null) {
    return { state: 'UNKNOWN', reason: 'UNKNOWN_INVALID_TIME_EVIDENCE', granted: false };
  }
  if (expiresAt <= assertedAt) {
    // A window that ends before it starts is not a coherent grant.
    return { state: 'UNKNOWN', reason: 'UNKNOWN_INVALID_TIME_EVIDENCE', granted: false };
  }

  const nowMs = parseInstant(now);
  if (nowMs === null) {
    return { state: 'UNKNOWN', reason: 'UNKNOWN_INVALID_TIME_EVIDENCE', granted: false };
  }

  if (nowMs >= expiresAt) {
    // The grant provably lapsed — a known terminal fact, distinct from
    // UNKNOWN because we have the source record that created it.
    return { state: 'EXPIRED', reason: 'AUTHORITY_EXPIRED', granted: false };
  }

  if (assertedState === 'GRANTED') {
    return { state: 'GRANTED', reason: 'AUTHORITY_GRANTED', granted: true };
  }

  // assertedState === 'EXPIRED' but the clock says the window is still open:
  // the source record and the clock disagree. Fail closed rather than pick.
  return { state: 'UNKNOWN', reason: 'UNKNOWN_UNRESOLVED', granted: false };
}

/**
 * Gate guard: authority is usable only when it is provably GRANTED.
 * Any other state — including DENIED, EXPIRED and UNKNOWN — denies.
 */
export function isAuthorityGranted(decision: AuthorityDecision): boolean {
  return decision.state === 'GRANTED' && decision.granted;
}

/** Authority derivation is read-only; it grants no effect capability. */
export interface AuthorityVocabularyCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const AUTHORITY_VOCABULARY_CAPABILITIES: AuthorityVocabularyCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
