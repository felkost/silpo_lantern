// Screen 3 of 3: the receipt.
//
// `unverified` is rendered as its own visible outcome, never as a
// success with a caveat: an unreachable or disagreeing read-back means
// the system does not KNOW the cart changed as consented (DR-12), and
// saying otherwise would be the exact "artificial 100% verified" claim
// the plan forbids.

import type { ReceiptEvent } from "../types";

interface Props {
  receipt: ReceiptEvent;
}

export function ReceiptScreen({ receipt }: Props) {
  const verified = receipt.status === "receipt";
  return (
    <section aria-labelledby="receipt-heading">
      <h2 id="receipt-heading">{verified ? "Готово" : "Не підтверджено"}</h2>
      {verified ? (
        <p data-testid="receipt-verified">
          Кошик змінено на{" "}
          <strong data-testid="actual-delta">{receipt.actual_delta} ₴</strong> —
          підтверджено повторним читанням кошика.
        </p>
      ) : (
        <p data-testid="receipt-unverified">
          Не вдалося підтвердити зміну кошика незалежним читанням. Це не
          означає, що зміни не сталося — перевірте кошик у застосунку Сільпо,
          перш ніж повторювати.
        </p>
      )}
      {receipt.reason && (
        <p>
          Причина: <span data-testid="receipt-reason">{receipt.reason}</span>
        </p>
      )}
      <p>
        <small>Оформлення та оплата залишаються вашою дією.</small>
      </p>
    </section>
  );
}
