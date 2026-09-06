// Screen 1 of 3: Diagnosis with its disclosure layer -- every validation
// the cart already carries, including the ones the app's own UI does not
// render (plan section 5.1, the product's whole point).

import type { DiagnosisEvent } from "../types";

interface Props {
  diagnosis: DiagnosisEvent | null;
  disclosures: string[];
}

export function DiagnosisScreen({ diagnosis, disclosures }: Props) {
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
            </p>
          )}
        </>
      )}

      <h3>Усі позначки кошика</h3>
      {disclosures.length === 0 ? (
        <p>Інших позначок немає.</p>
      ) : (
        <ul data-testid="disclosures">
          {disclosures.map((code) => (
            <li key={code}>{code}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
