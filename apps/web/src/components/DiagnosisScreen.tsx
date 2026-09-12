// Screen 1 of 3: Diagnosis with its disclosure layer -- every validation
// the cart already carries, including the ones the app's own UI does not
// render (plan section 5.1, the product's whole point), plus the
// delivery-channel comparison (amendment A7).
//
// the SSE `diagnosis` event now actually carries
// `validations`/`channels` (it used to be dropped before reaching this
// component at all -- an adversarial audit of the stage plan caught it),
// and both are rendered in Ukrainian rather than as raw validation codes.

import { translateValidationCode } from "../copy";
import type { DiagnosisEvent, DisclosedValidation } from "../types";

interface Props {
  diagnosis: DiagnosisEvent | null;
}

function groupByCode(
  validations: DisclosedValidation[],
): Array<[DisclosedValidation, number]> {
  const groups = new Map<string, [DisclosedValidation, number]>();
  for (const v of validations) {
    const entry = groups.get(v.code);
    if (entry) {
      entry[1] += 1;
    } else {
      groups.set(v.code, [v, 1]);
    }
  }
  return [...groups.values()];
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
          {diagnosis.primary_code === null && (
            <p className="muted" data-testid="unknown-reason">
              Жоден результат перевірки кошика не є відомим правилом, тому система не
              пропонує дію наосліп — перевірте кошик у застосунку Сільпо.
            </p>
          )}
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

          <h3>Усі результати перевірок кошика</h3>
          {diagnosis.validations.length === 0 ? (
            <p>Інших результатів перевірок немає.</p>
          ) : (
            <ul data-testid="disclosures">
              {/* Identical lines grouped with a count: a cart with ten
                  out-of-stock items produced ten identical sentences on
                  the first live screen. */}
              {groupByCode(diagnosis.validations).map(([validation, count]) => (
                <li key={validation.code} data-testid={`validation-${validation.code}`}>
                  {translateValidationCode(validation)}
                  {count > 1 && <span className="muted"> × {count}</span>}
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
