// Screen 2 of 3: item-bound consent.
//
// B2's load-bearing rule: every NUMBER the guest sees here comes from the
// proposal's own typed fields (`product_name`, `quantity`,
// `expected_delta`) -- computed in code, carried through the same
// `canonical_args` the consent's `args_hash` binds. `guest_text_uk` is
// the explainer model's rendered sentence and is displayed as framing
// only, never as the source of a figure: a guest who agrees to what a
// model wrote, while a different payload executes, has not actually
// consented to the write.

import type { Candidate, ReceiptEvent } from "../types";
import { Icon } from "./Icon";

interface Props {
  candidates: Candidate[];
  onConsent: (actionId: string) => void;
  /** «Не додавати нічого»: the Customer declines every option. Nothing is
   * written; the session stays paused at the guard with no consent. */
  onDecline?: () => void;
  submitting: boolean;
  /** a second consent+write round means the guest
   * may already have one round's receipt by the time this screen shows
   * again -- shown here so it is not lost between rounds. */
  priorReceipts?: ReceiptEvent[];
}

export function ConsentScreen({
  candidates,
  onConsent,
  onDecline,
  submitting,
  priorReceipts = [],
}: Props) {
  // every candidate on this screen is either an ordinary "add"
  // or a compensation offer -- never a mix (persist_receipt_node REPLACES
  // candidates, never appends across kinds), so checking the first entry
  // is enough to decide which screen this is.
  const isCompensationOffer =
    candidates.length > 0 && candidates.every((c) => c.kind === "compensate");

  return (
    <section aria-labelledby="consent-heading">
      {priorReceipts.length > 0 && (
        <div data-testid="prior-receipts">
          <h3>Попередні зміни цього сеансу</h3>
          <ul>
            {priorReceipts.map((receipt, index) => {
              const delta = receipt.actual_delta ? Number(receipt.actual_delta) : null;
              const isCompensation = delta !== null && delta < 0;
              return (
                <li key={index} data-testid={`prior-receipt-${index}`}>
                  {receipt.status !== "receipt"
                    ? "Не підтверджено"
                    : isCompensation
                      ? `Повернуто на ${Math.abs(delta as number)} ₴`
                      : `Додано на ${receipt.actual_delta} ₴`}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <h2 id="consent-heading">
        {isCompensationOffer ? "Повернути кошик як було?" : "Оберіть, що додати"}
      </h2>
      {isCompensationOffer && (
        <p data-testid="compensation-lede">
          Оформлення досі недоступне. Можемо прибрати те, що ми додали, і повернути
          кошик до попереднього стану — це окрема дія, і потрібна ваша нова згода.
          Це стосується лише нашої власної зміни, нічого іншого в кошику не
          торкнеться.
        </p>
      )}
      <ul>
        {candidates.map((candidate) => (
          <li key={candidate.action_id} data-testid={`candidate-${candidate.action_id}`}>
            <p>
              <strong data-testid="product-name">{candidate.product_name}</strong>
            </p>
            <p>
              Кількість: <span data-testid="quantity">{candidate.quantity}</span>
            </p>
            <p>
              Очікувана зміна суми:{" "}
              <span data-testid="expected-delta">{candidate.expected_delta} ₴</span>
            </p>
            {candidate.guest_text_uk !== "" && (
              <p data-testid="guest-text">
                <em>{candidate.guest_text_uk}</em>
              </p>
            )}
            <button
              type="button"
              disabled={submitting}
              onClick={() => onConsent(candidate.action_id)}
            >
              {isCompensationOffer
                ? "Повернути як було"
                : `Додати «${candidate.product_name}» за ${candidate.expected_delta} ₴`}
            </button>
          </li>
        ))}
      </ul>
      {onDecline && (
        <p>
          <button
            type="button"
            className="quiet small"
            disabled={submitting}
            onClick={onDecline}
            data-testid="decline-all"
            title="Жодного варіанта не обрано; кошик лишається як був"
          >
            <Icon name="decline" /> {isCompensationOffer ? "Залишити як є" : "Не додавати нічого"}
          </button>
        </p>
      )}
      <p>
        <small>
          Оформлення й оплату завжди робите ви — застосунок лише змінює кошик за
          вашою згодою.
        </small>
      </p>
    </section>
  );
}
