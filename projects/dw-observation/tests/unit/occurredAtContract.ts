// RED assertion helper: the canonical producer (TaskController/GWC) MUST supply
// the source occurred_at; Postgres must NOT fabricate it via DEFAULT now() or
// any other DB-generated timestamp.
//
// We parse the raw SQL text (lowercased by the contract test harness) and reject
// any DEFAULT that looks like now(), current_timestamp, clock_timestamp, or
// any other function call for occurred_at. A bare DEFAULT <literal> is allowed
// only if it is not a call — but the canonical contract requires NO DEFAULT at
// all, so we reject any DEFAULT on occurred_at.
//
// NOTE: this module is test-only and is imported by the contract test. It must
// not be referenced by production code paths.

interface OccurredAtSpec {
  hasTimestampType: boolean;
  hasNotNull: boolean;
  hasDefault: boolean;
  defaultExpression: string; // lowercased text of the DEFAULT expression, or ""
  defaultIsCall: boolean;    // true if DEFAULT is a function call (now/current/clock/...)
  rawColumnDef: string;      // the full column definition text (lowercased)
}

export function parseOccurredAt(sql: string): OccurredAtSpec {
  // Find the occurred_at column definition.
  // We operate on the lowercased sql from the test harness.
  const colRe = /occurred_at\s+timestamptz\s+not\s+null(?:\s+\S+)*/i;
  const m = sql.match(colRe);
  if (!m) {
    return {
      hasTimestampType: false,
      hasNotNull: false,
      hasDefault: false,
      defaultExpression: "",
      defaultIsCall: false,
      rawColumnDef: "",
    };
  }
  const def = m[0];
  const hasTimestampType = /timestamptz/i.test(def);
  const hasNotNull = /\bnot\s+null\b/i.test(def);
  const defaultM = def.match(/\bdefault\s+(.+)$/i);
  const hasDefault = !!defaultM;
  const defaultExpression = hasDefault ? defaultM[1].trim() : "";
  const defaultIsCall =
    hasDefault &&
    /^\s*\w[\w.]*\s*\(/.test(defaultExpression); // function call
  return {
    hasTimestampType,
    hasNotNull,
    hasDefault,
    defaultExpression,
    defaultIsCall,
    rawColumnDef: def,
  };
}

/**
 * Canonical contract assertion (BLOCKER A):
 * occurred_at must be TIMESTAMPTZ NOT NULL with NO DEFAULT at all.
 *
 * The source system supplies the timestamp; Postgres must not fabricate it.
 * Any DEFAULT now()/current_timestamp/clock_timestamp/... is prohibited.
 */
export function assertOccurredAtContract(spec: OccurredAtSpec): string {
  if (!spec.hasTimestampType) {
    return "occurred_at must be TIMESTAMPTZ";
  }
  if (!spec.hasNotNull) {
    return "occurred_at must be NOT NULL";
  }
  if (spec.hasDefault) {
    if (spec.defaultIsCall) {
      return (
        `occurred_at must NOT have a DB-generated DEFAULT (${spec.defaultExpression}); ` +
        "the canonical producer supplies the source timestamp"
      );
    }
    return (
      `occurred_at must NOT have any DEFAULT (${spec.defaultExpression}); ` +
      "the canonical producer supplies the source timestamp"
    );
  }
  return ""; // satisfied
}
