// Screen 3 of 3: the receipt.
//
// `unverified` is rendered as its own visible outcome, never as a
// success with a caveat: an unreachable or disagreeing read-back means
// the system does not KNOW the cart changed as consented (DR-12), and
// saying otherwise would be the exact "artificial 100% verified" claim
// the plan forbids.
//
// G7 (D-G7-05): renders every round's receipt, not just the last -- the
// second consent+write round (D42) can produce a second receipt in the
// same session, and the first one is real proof that must not vanish.

import { translateErrorReason } from "../copy";
import type { ReceiptEvent } from "../types";

interface Props {
  receipts: ReceiptEvent[];
}

function OneReceipt({ receipt, roundNumber }: { receipt: ReceiptEvent; roundNumber: number }) {
  const verified = receipt.status === "receipt";
  const uaReason = translateErrorReason(receipt.reason);
  return (
    <article aria-labelledby={`receipt-heading-${roundNumber}`}>
      <h3 id={`receipt-heading-${roundNumber}`}>
        {roundNumber > 1 ? `Раунд ${roundNumber}: ` : ""}
        {verified ? "Готово" : "Не підтверджено"}
      </h3>
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
      {/* D42: a verified write is not a recovered cart -- a live run
          produced a correct write that left the guest 2.98 short of the
          threshold. The guest is told which of the two happened. */}
      {verified && !receipt.blocker_cleared && (
        <p data-testid="blocker-not-cleared">
          Кошик усе ще не досягає мінімальної суми
          {receipt.remaining_gap !== null && (
            <>
              {" "}
              — не вистачає <strong>{receipt.remaining_gap} ₴</strong>
            </>
          )}
          . Оформлення поки недоступне.
        </p>
      )}
      {uaReason && (
        <p>
          Причина: <span data-testid="receipt-reason">{uaReason}</span>
        </p>
      )}
      <p>
        <small>Оформлення та оплата залишаються вашою дією.</small>
      </p>
    </article>
  );
}

export function ReceiptScreen({ receipts }: Props) {
  return (
    <section aria-labelledby="receipt-section-heading">
      <h2 id="receipt-section-heading">Результат</h2>
      {receipts.map((receipt, index) => (
        <OneReceipt key={index} receipt={receipt} roundNumber={index + 1} />
      ))}
    </section>
  );
}
