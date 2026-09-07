// Mirrors apps/api's own response shapes and the five SSE event names
// plan section 1.5 declares (and apps/api/sse-events.schema.json now
// enforces as a closed enum, with per-event `data` shapes for
// `diagnosis` and `receipt` since G7 -- D-G7-03).

export interface Candidate {
  action_id: string;
  product_name: string;
  /** Decimal-as-string on the wire: the guest's consented increment. */
  quantity: string;
  /** Decimal-as-string: price * increment, computed in code, never by an LLM. */
  expected_delta: string;
  /** The explainer's rendered Ukrainian sentence -- framing only. */
  guest_text_uk: string;
}

export interface CreateSessionResponse {
  session_id: string;
  status: string;
  /** A fresh session has no guest token yet -- the guest logs in first. */
  authorized: boolean;
  /** Where to send the guest for Silpo's own phone + OTP login. */
  auth_url: string;
}

export interface ConsentAckResponse {
  status: string;
  action_id: string;
}

export interface EventEnvelope {
  session_id: string;
  trace_id: string;
  version: Record<string, string>;
}

/** One entry of the disclosure layer -- every validation the cart already
 * carries, blockers and non-blockers alike (plan section 5.1). */
export interface DisclosedValidation {
  code: string;
  level: "error" | "warning" | "info";
  type: string;
}

/** One row of the delivery-channel comparison (amendment A7). */
export interface ChannelComparisonRow {
  delivery_type: string;
  /** Decimal-as-string: this channel's own gap to its minOrderCost. */
  gap: string;
  verdict: "clears_now" | "needs_check";
  reason: string;
}

export interface DiagnosisEvent extends EventEnvelope {
  primary_code: string | null;
  gap: string | null;
  gap_is_borderline: boolean;
  validations: DisclosedValidation[];
  channels: ChannelComparisonRow[];
}

export interface OptionsEvent extends EventEnvelope {
  candidates: Candidate[];
}

export interface ReceiptEvent extends EventEnvelope {
  status: string;
  reason: string | null;
  actual_delta: string | null;
  /** D42: a verified write is not a recovered cart -- distinguishes
   * "the write landed" from "you can check out". */
  blocker_cleared: boolean;
  remaining_gap: string | null;
}

export interface ErrorEvent extends EventEnvelope {
  error: string | null;
}

export type Screen =
  | "idle"
  | "auth_required"
  | "diagnosis"
  | "consent"
  | "receipt"
  | "error";
