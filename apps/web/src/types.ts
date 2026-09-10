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
  /** G8 (D51): "add" is the ordinary consent screen; "compensate" is the
   * offer to undo a write this system already performed -- the client
   * branches its copy on this, never inferring it from anything else. */
  kind: "add" | "compensate";
  /** Set only for kind="compensate": the action_id of the receipt this
   * candidate undoes. */
  compensates_action_id: string | null;
  /** G10 (claim 3): computed server-side with the guard's own canonicalizer. */
  args_hash: string;
  tool_name: string;
  evidence: EvidenceTuple[];
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
  /** G10 (claim 3): the binding as recorded server-side. No cart id, ever. */
  args_hash: string;
  state_hash: string;
  expires_at: string;
}

/** G10: one evidence tuple behind a candidate -- price, its source and its
 * age. Deliberately without a product id. */
export interface EvidenceTuple {
  price: string;
  availability: boolean;
  source_tool: string;
  captured_at: string;
}

/** G10: `GET /evidence` -- measured earlier, never this session. */
export interface MetricRow {
  name: string;
  value: number | null;
  n: number;
  interval: [number, number] | null;
  caveat: string;
}

export interface EvidenceResponse {
  population: string;
  generated_at: string;
  regenerate: string;
  metrics: MetricRow[];
  disclosure: {
    state: string;
    observed_at: string;
    products_total: number | null;
    app_showed: string[];
    validations: Array<{ code: string; level: string; rendered_by_app: boolean }>;
  };
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
  /** G10: whether the policy registry knows this code. */
  is_known?: boolean;
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
  /** G10 (claim 2): the arithmetic's inputs, as decimal strings. */
  products_total: string | null;
  threshold_source: "validation_context" | "time_slots" | "unverified";
  validations: DisclosedValidation[];
  channels: ChannelComparisonRow[];
}

export interface OptionsEvent extends EventEnvelope {
  candidates: Candidate[];
}

export interface ReceiptEvent extends EventEnvelope {
  status: string;
  reason: string | null;
  /** G10 (claim 4): expected against actual, and the typed outcome. */
  expected_delta: string | null;
  verified: boolean;
  kind: "add" | "compensate" | null;
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
