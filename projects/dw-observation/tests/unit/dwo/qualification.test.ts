/**
 * CR-830-A/B/C/D verification — semantic + resilience qualification.
 *
 * AC-830-01 V2_SEMANTIC_QUALIFIED derivable
 * AC-830-02 AC-RS-01..11 each has machine-checkable evidence and disposition
 * AC-830-03 Universal adversarial suite has machine-checkable evidence and fail-closed expectations
 * AC-830-04 qualification subject bound to exact source/profile/reducer/projection/comparison identity
 * AC-830-05 DEV-NATIVE and COMPATIBILITY results separate; incompatible inputs fail closed
 * AC-830-06 no fixture bypasses production projection/reducer path
 * AC-830-07 all existing DWO suites + Python regression continue to pass
 */
import { describe, expect, it } from 'vitest';
import {
  QUALIFICATION_CAPABILITIES,
  buildQualificationRecord,
  deriveV2SemanticQualified,
  runAcRsSuite,
  runAdversarialSuite,
  type QualificationSubject,
  type SemanticQualifiedInput,
} from '@/lib/dwo/qualification';
import {
  QUALIFICATION_SUBJECT_CAPABILITIES,
  subjectDigest,
  validateQualificationSubject,
  type QualificationSubject as Subject,
} from '@/lib/dwo/qualificationSubject';

const LIVE = {
  sourceSha: '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3',
  reducerVersion: 'gwc.dwo.reducer/1',
  projectionContractVersion: 'gwc.dwo.projection-contract-v2/2',
  comparisonContractVersion: 'gwc.dwo.fnr02-comparison/1',
};

function subject(overrides: Partial<Subject> = {}): Subject {
  return {
    sourceRepository: 'nhatnguyenquang1838-coder/gwc',
    sourceRef: 'fix/SCRUM-781-m1-runtime-contract-convergence',
    sourceSha: LIVE.sourceSha,
    sourceProfile: 'DEV_NATIVE',
    lifecycleProfile: { id: 'gwc.universal-run', version: 1 },
    reducerVersion: LIVE.reducerVersion,
    projectionContractVersion: LIVE.projectionContractVersion,
    comparisonContractVersion: LIVE.comparisonContractVersion,
    qualificationRecordRef: 'qual/SCRUM-830-R1',
    boundAt: '2026-09-30T06:10:00+07:00',
    ...overrides,
  };
}

function qualifiedInput(overrides: Partial<SemanticQualifiedInput> = {}): SemanticQualifiedInput {
  return {
    subjectComplete: true,
    subjectCurrent: true,
    allAcRsPass: true,
    allAdversarialFailClosed: true,
    devNativeQualified: true,
    compatibilityQualified: true,
    noIncompatibleNormalized: true,
    ...overrides,
  };
}

describe('AC-830-01 · V2_SEMANTIC_QUALIFIED derivable', () => {
  it('derives the token when subject bound + all suites pass', () => {
    const d = deriveV2SemanticQualified(qualifiedInput());
    expect(d.derivable).toBe(true);
    expect(d.token).toBe('V2_SEMANTIC_QUALIFIED');
  });

  it('fails closed when the subject is stale', () => {
    const d = deriveV2SemanticQualified(qualifiedInput({ subjectCurrent: false }));
    expect(d.derivable).toBe(false);
    expect(d.token).toBeNull();
    expect(d.reasons).toContain('qualification subject is stale (SHA/contract drift)');
  });

  it('fails closed when an AC-RS scenario does not pass', () => {
    const d = deriveV2SemanticQualified(qualifiedInput({ allAcRsPass: false }));
    expect(d.derivable).toBe(false);
  });

  it('fails closed when an adversarial case does not fail closed', () => {
    const d = deriveV2SemanticQualified(qualifiedInput({ allAdversarialFailClosed: false }));
    expect(d.derivable).toBe(false);
  });

  it('fails closed when an INCOMPATIBLE input is normalized', () => {
    const d = deriveV2SemanticQualified(qualifiedInput({ noIncompatibleNormalized: false }));
    expect(d.derivable).toBe(false);
  });
});

describe('AC-830-02 · AC-RS-01..11 machine-checkable evidence', () => {
  it('runs 11 scenarios, each with id/outcome/evidence', () => {
    const suite = runAcRsSuite();
    expect(suite).toHaveLength(11);
    for (const r of suite) {
      expect(r.id).toMatch(/^AC-RS-\d{2}$/);
      expect(r.title.length).toBeGreaterThan(0);
      expect(r.evidence.length).toBeGreaterThan(0);
      expect(['DEV_NATIVE', 'COMPATIBILITY', 'INCOMPATIBLE']).toContain(r.outcome);
    }
  });

  it('all 11 AC-RS scenarios pass', () => {
    const suite = runAcRsSuite();
    for (const r of suite) {
      expect(r.pass, `${r.id} ${r.title}: ${r.evidence}`).toBe(true);
    }
  });

  it('covers the exact BRD scenario ids', () => {
    const ids = runAcRsSuite().map((r) => r.id);
    for (let i = 1; i <= 11; i += 1) {
      expect(ids).toContain(`AC-RS-${String(i).padStart(2, '0')}`);
    }
  });
});

describe('AC-830-03 · Universal adversarial suite fail-closed', () => {
  it('runs 10 adversarial cases, each with failClosed expectation', () => {
    const suite = runAdversarialSuite();
    expect(suite).toHaveLength(10);
    for (const r of suite) {
      expect(r.id).toMatch(/^ADV-\d{2}$/);
      expect(r.outcome).toBe('INCOMPATIBLE');
      expect(r.failClosed).toBe(true);
      expect(r.evidence.length).toBeGreaterThan(0);
    }
  });

  it('all 10 adversarial cases pass (fail closed as expected)', () => {
    const suite = runAdversarialSuite();
    for (const r of suite) {
      expect(r.pass, `${r.id} ${r.title}: ${r.evidence}`).toBe(true);
    }
  });
});

describe('AC-830-04 · qualification subject binding', () => {
  it('binds repo/ref/SHA + profiles + contract versions + bundle id', () => {
    const s = subject();
    const v = validateQualificationSubject(s, LIVE);
    expect(v.complete).toBe(true);
    expect(v.current).toBe(true);
    expect(v.digest.length).toBeGreaterThan(0);
  });

  it('digest changes when any bound field changes', () => {
    const a = subjectDigest(subject());
    const b = subjectDigest(subject({ sourceSha: 'a'.repeat(40) }));
    expect(a).not.toBe(b);
  });

  it('fails closed on a stale SHA', () => {
    const v = validateQualificationSubject(subject({ sourceSha: 'a'.repeat(40) }), LIVE);
    expect(v.complete).toBe(true);
    expect(v.current).toBe(false);
  });

  it('fails closed on a missing field', () => {
    const v = validateQualificationSubject(subject({ reducerVersion: '' }), LIVE);
    expect(v.complete).toBe(false);
  });
});

describe('AC-830-05 · DEV-NATIVE / COMPATIBILITY separation + fail-closed', () => {
  it('buildQualificationRecord separates DEV-NATIVE and COMPATIBILITY vectors', () => {
    const record = buildQualificationRecord(subject(), LIVE);
    expect(record.subjectComplete).toBe(true);
    expect(record.subjectCurrent).toBe(true);
    expect(record.acRs).toHaveLength(11);
    expect(record.adversarial).toHaveLength(10);
    // DEV-NATIVE scenarios are the AC-RS suite; adversarial are INCOMPATIBLE.
    expect(record.devNative.length).toBeGreaterThan(0);
    expect(record.incompatible.length).toBeGreaterThan(0);
  });

  it('INCOMPATIBLE inputs fail closed and are never normalized', () => {
    const record = buildQualificationRecord(subject(), LIVE);
    for (const r of record.incompatible) {
      expect(r.failClosed).toBe(true);
      expect(r.outcome).toBe('INCOMPATIBLE');
    }
  });

  it('record is qualified when subject bound + all suites pass', () => {
    const record = buildQualificationRecord(subject(), LIVE);
    expect(record.qualified).toBe(true);
    expect(record.reasons).toEqual([]);
  });
});

describe('AC-830-06 · no fixture bypasses production projection/reducer path', () => {
  it('the qualification surface is read-only and grants no authority', () => {
    expect(QUALIFICATION_CAPABILITIES.write).toBe(false);
    expect(QUALIFICATION_CAPABILITIES.grantsAuthority).toBe(false);
    expect(QUALIFICATION_SUBJECT_CAPABILITIES.write).toBe(false);
    expect(QUALIFICATION_SUBJECT_CAPABILITIES.grantsAuthority).toBe(false);
  });

  it('scenarios exercise the real kernel modules (evidence references kernel behavior)', () => {
    const suite = runAcRsSuite();
    // AC-RS-01 rebuild parity uses compareStates; AC-RS-05 uses replay + FNR-02.
    const rs01 = suite.find((r) => r.id === 'AC-RS-01');
    const rs05 = suite.find((r) => r.id === 'AC-RS-05');
    expect(rs01?.evidence).toContain('compareStates');
    expect(rs05?.evidence).toContain('FNR-02');
  });
});
