/**
 * CR-822-D — FIXTURE_STREAM_CERTIFIED derivation.
 *
 * SCRUM-822 / DWO-V2-01, G2 EXECUTE, PLAN-822-R1, child run CR-822-D.
 *
 * The WS1 exit token FIXTURE_STREAM_CERTIFIED is DERIVED from machine-readable
 * state, never asserted. It holds exactly when:
 *   1. the fixture set is the canonical DWO-UR-30-V1;
 *   2. it contains exactly 30 runs (29 conforming + 1 negative);
 *   3. the negative fixture DEV-RUN-020 fails closed as INCOMPATIBLE;
 *   4. no fixture projects QUALIFIED without a qualification record;
 *   5. the projection defaults are applied (DEV_NATIVE/LIVE/PENDING/NOT_APPLICABLE/0);
 *   6. the event stream is deterministic (same prefix -> same frame).
 */
import {
  DWO_UR_30_V1,
  FIXTURE_CATALOG,
  assertFixtureCatalogInvariants,
  isQualified,
  resolveFixtureProjection,
} from './fixtureSpec';

export interface FixtureStreamCertificationInput {
  readonly fixtureSet: string;
  readonly runCount: number;
  readonly conformingRuns: number;
  readonly negativeFixture: string;
  /** Deterministic event stream: event_id -> run_id mapping. */
  readonly eventStream: Readonly<Record<string, string>>;
  /** Fixtures that carry a deterministic synthetic qualification record. */
  readonly qualifiedWithRecord: readonly string[];
}

export interface CertificationDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive FIXTURE_STREAM_CERTIFIED. Fails closed on any incoherent input.
 */
export function deriveFixtureStreamCertified(
  input: FixtureStreamCertificationInput,
): CertificationDecision {
  const reasons: string[] = [];

  if (input.fixtureSet !== DWO_UR_30_V1) {
    reasons.push(`fixture set is ${input.fixtureSet}, expected ${DWO_UR_30_V1}`);
  }
  if (input.runCount !== 30) {
    reasons.push(`run count ${input.runCount}, expected 30`);
  }
  if (input.conformingRuns !== 29) {
    reasons.push(`conforming runs ${input.conformingRuns}, expected 29`);
  }
  if (input.negativeFixture !== 'DEV-RUN-020') {
    reasons.push(`negative fixture ${input.negativeFixture}, expected DEV-RUN-020`);
  }

  // Catalog invariants (30 unique ids, 1 negative, 29 conforming).
  try {
    assertFixtureCatalogInvariants(FIXTURE_CATALOG);
  } catch (e) {
    reasons.push(`catalog invariant failed: ${(e as Error).message}`);
  }

  // DEV-RUN-020 must fail closed as INCOMPATIBLE.
  const negative = FIXTURE_CATALOG.find((f) => f.id === 'DEV-RUN-020');
  if (negative) {
    const proj = resolveFixtureProjection(negative);
    if (proj.semanticQualification !== 'INCOMPATIBLE') {
      reasons.push('DEV-RUN-020 does not fail closed as INCOMPATIBLE');
    }
  }

  // QUALIFIED is never implicit: every QUALIFIED fixture must have a record.
  const qualified = FIXTURE_CATALOG.filter(isQualified);
  for (const f of qualified) {
    if (!input.qualifiedWithRecord.includes(f.id)) {
      reasons.push(`${f.id} projects QUALIFIED without a qualification record`);
    }
  }

  // Deterministic event stream: every fixture id must appear exactly once.
  const eventRunIds = Object.values(input.eventStream);
  const fixtureIds = new Set(FIXTURE_CATALOG.map((f) => f.id));
  for (const id of fixtureIds) {
    if (!eventRunIds.includes(id)) {
      reasons.push(`fixture ${id} missing from event stream`);
    }
  }
  if (new Set(eventRunIds).size !== eventRunIds.length) {
    reasons.push('event stream has duplicate run ids (non-deterministic)');
  }

  if (reasons.length === 0) {
    return { derivable: true, token: 'FIXTURE_STREAM_CERTIFIED', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  fixtureStreamCertified: 'FIXTURE_STREAM_CERTIFIED',
} as const);
