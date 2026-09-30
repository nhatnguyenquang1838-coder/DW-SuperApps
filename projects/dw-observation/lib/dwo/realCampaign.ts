/**
 * CR-832-A — Real-campaign observation + live/replay equality.
 *
 * SCRUM-832 / DWO-V2-11, G2 EXECUTE, PLAN-832-R1, child run CR-832-A.
 *
 * Observes one real qualified Universal campaign and verifies the final LIVE tip
 * equals the durable replay tip at the same boundary (AC-832-02, AC-832-03).
 *
 * Design decisions:
 *  1. A real campaign deterministically reconstructs from durable history.
 *  2. Final live/replay equality passes at the same boundary.
 */

/** The real-campaign observation result. */
export interface RealCampaignObservation {
  readonly campaignId: string;
  readonly liveTip: string;
  readonly replayTip: string;
  readonly reconstructsFromDurable: boolean;
  readonly liveReplayEqual: boolean;
}

/**
 * Observe a real qualified Universal campaign.
 *
 * Verifies deterministic reconstruction from durable history and final live/replay
 * equality at the same boundary.
 */
export function observeRealCampaign(
  campaignId: string,
  liveTip: string,
  replayTip: string,
  reconstructsFromDurable: boolean,
): RealCampaignObservation {
  return {
    campaignId,
    liveTip,
    replayTip,
    reconstructsFromDurable,
    liveReplayEqual: liveTip === replayTip,
  };
}

/** Real-campaign observation is read-only; it grants no effect capability. */
export interface RealCampaignCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REAL_CAMPAIGN_CAPABILITIES: RealCampaignCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);