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

import type { Candidate } from "../types";

interface Props {
  candidates: Candidate[];
  onConsent: (actionId: string) => void;
  submitting: boolean;
}

export function ConsentScreen({ candidates, onConsent, submitting }: Props) {
  return (
    <section aria-labelledby="consent-heading">
      <h2 id="consent-heading">Оберіть, що додати</h2>
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
              Очікувана сума:{" "}
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
              Додати «{candidate.product_name}» за {candidate.expected_delta} ₴
            </button>
          </li>
        ))}
      </ul>
      <p>
        <small>
          Оформлення й оплату завжди робите ви — застосунок лише змінює кошик за
          вашою згодою.
        </small>
      </p>
    </section>
  );
}
