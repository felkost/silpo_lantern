// Screen 1 of 3: Diagnosis with its disclosure layer -- every validation
// the cart already carries, including the ones the app's own UI does not
// render (plan section 5.1, the product's whole point), plus the
// delivery-channel comparison (amendment A7).
//
// G7 (D-G7-03/D-G7-04): the SSE `diagnosis` event now actually carries
// `validations`/`channels` (it used to be dropped before reaching this
// component at all -- an adversarial audit of the G7 plan caught it),
// and both are rendered in Ukrainian rather than as raw validation codes.

import { translateValidationCode } from "../copy";
import type { DiagnosisEvent } from "../types";

interface Props {
  diagnosis: DiagnosisEvent | null;
}

export function DiagnosisScreen({ diagnosis }: Props) {
  return (
    <section aria-labelledby="diagnosis-heading">
      <h2 id="diagnosis-heading">Що блокує оформлення</h2>
      {diagnosis === null ? (
        <p>Читаємо кошик…</p>
      ) : (
        <>
          <p>
            Причина:{" "}
            <code data-testid="primary-code">{diagnosis.primary_code ?? "невідома"}</code>
          </p>
          {diagnosis.gap !== null && (
            <p>
              Не вистачає:{" "}
              <strong data-testid="gap">{diagnosis.gap} ₴</strong>
              {diagnosis.gap_is_borderline && (
                <span data-testid="gap-borderline">
                  {" "}
                  (сума на межі порогу -- перевірте кошик самостійно)
                </span>
              )}
            </p>
          )}

          <h3>Усі позначки кошика</h3>
          {diagnosis.validations.length === 0 ? (
            <p>Інших позначок немає.</p>
          ) : (
            <ul data-testid="disclosures">
              {diagnosis.validations.map((validation) => (
                <li key={validation.code} data-testid={`validation-${validation.code}`}>
                  {translateValidationCode(validation)}
                </li>
              ))}
            </ul>
          )}

          {diagnosis.channels.length > 0 && (
            <>
              <h3>Порівняння способів доставки</h3>
              <ul data-testid="channels">
                {diagnosis.channels.map((row) => (
                  <li
                    key={row.delivery_type}
                    data-testid={`channel-${row.delivery_type}`}
                  >
                    <strong>{row.delivery_type}</strong>:{" "}
                    {row.verdict === "clears_now" ? (
                      <span data-testid="channel-clears">
                        уже підходить під мінімальну суму
                      </span>
                    ) : (
                      <span>потребує перевірки -- {row.reason}</span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
