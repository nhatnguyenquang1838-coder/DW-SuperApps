/**
 * CR-825-A — Append-only durable event order + explicit position/watermark.
 *
 * SCRUM-825 / DWO-V2-04, G2 EXECUTE, PLAN-825-R1, child run CR-825-A.
 *
 * The durable foundation: append-only event order with an explicit durable
 * position/watermark. Durable history is sufficient to reconstruct accepted
 * projection state (AC-825-03).
 *
 * Design decisions:
 *  1. Events are append-only; each has a monotonic durable ordinal.
 *  2. A watermark is the highest contiguous durable position applied. It is the
 *     explicit sync position for reconstruction.
 *  3. The durable order is the canonical reconstruction source; derived state is a
 *     pure function of it.
 */

/** A durable event with an explicit position. */
export interface DurableEvent {
  readonly eventId: string;
  readonly runId: string;
  readonly ordinal: number;
  readonly payload: unknown;
}

/** The durable watermark: highest contiguous position applied. */
export interface DurableWatermark {
  readonly position: number;
  readonly contiguous: boolean;
}

/** Append-only durable event log. */
export class DurableLog {
  private readonly events: DurableEvent[] = [];

  /** Append an event. Returns the new durable position. */
  append(event: DurableEvent): number {
    this.events.push(event);
    return this.events.length;
  }

  /** Read the durable log (append-only; no mutation). */
  read(): readonly DurableEvent[] {
    return this.events;
  }

  /** The current durable position (count of appended events). */
  position(): number {
    return this.events.length;
  }

  /**
   * Compute the watermark: the highest contiguous position applied.
   *
   * Events are applied in ordinal order. A gap (missing ordinal) makes the
   * watermark non-contiguous at the gap.
   */
  watermark(): DurableWatermark {
    const ordered = [...this.events].sort((a, b) => a.ordinal - b.ordinal);
    let position = 0;
    let contiguous = true;
    for (const e of ordered) {
      if (e.ordinal === position + 1) {
        position = e.ordinal;
      } else {
        contiguous = false;
        break;
      }
    }
    return { position, contiguous };
  }
}

/** Durable order is read-only data; it grants no effect capability. */
export interface DurableOrderCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DURABLE_ORDER_CAPABILITIES: DurableOrderCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
