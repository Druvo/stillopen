import { request } from "@/lib/api";
import type { Finding } from "./api";

export type ParsedFields = { company: string; role: string; location: string; pay: string; deadline: string; link: string };
export type ParsedPosting = { fields: ParsedFields; found: (keyof ParsedFields)[]; found_by_ai: (keyof ParsedFields)[]; method: "rules" | "ai"; notice: string; message: string };

export type OfferDifferences = { currency: string; lines: string[] };
export type CounterNote = { subject: string; body: string; for_offer: number; flagged: Finding[]; flagged_count: number };
export type OfferNote = { differences: OfferDifferences[]; ask_about: string[]; counter_note: CounterNote | null; ai: boolean; notice: string; counter_message: string };

export type ReferralDraftResult = { subject: string; body: string; to: string; method: "template" | "ai"; flagged: Finding[]; flagged_count: number; notice: string };

export const extrasApi = {
  parseText: (text: string) => request<ParsedPosting>("POST", "/jobs/parse-text", { text }),
  compareOffers: (offerIds: number[], counterOfferId?: number | null) =>
    request<OfferNote>("POST", "/offers/compare-note", counterOfferId ? { offer_ids: offerIds, counter_offer_id: counterOfferId } : { offer_ids: offerIds }),
  referralDraft: (contactId: number, jobId: number, polish: boolean) => request<ReferralDraftResult>("POST", `/contacts/${contactId}/referral-draft`, { job_id: jobId, polish }),
};
