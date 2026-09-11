// The starting state, as the server returned it (2026-09-11, the author):
// a jury cannot be shown the Silpo app itself, so the console shows the
// cart -- lines, total, minimum, slot -- and, once evidence is loaded,
// what the app showed beside what the server returned. Guest-facing
// Ukrainian. Product names are allowed; nothing here identifies the guest.

import type { DiagnosisEvent, EvidenceResponse } from "../types";

interface Props {
  diagnosis: DiagnosisEvent | null;
  evidence: EvidenceResponse | null;
}

function slot(start: string | null, end: string | null): string {
  if (!start || !end) {
    return "не обрано";
  }
  const s = new Date(start);
  const e = new Date(end);
  const day = s.toISOString().slice(0, 10);
  const hm = (d: Date) => d.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
  return `${day}, ${hm(s)}–${hm(e)}`;
}

export function CartColumn({ diagnosis, evidence }: Props) {
  const cart = diagnosis?.cart ?? null;
  return (
    <aside className="cart-column" aria-label="Стан кошика" data-testid="cart-column">
      <section className="panel-block">
        <h2>Стан кошика</h2>
        <p className="muted uk">
          Так кошик бачить сервер Сільпо в момент читання — це вихідні дані, з яких
          починається сценарій. Застосунок Сільпо в кадрі не показуємо.
        </p>
        {cart === null ? (
          <p className="muted">Кошик ще не прочитано.</p>
        ) : (
          <>
            <ul className="plain cart-lines">
              {cart.lines.map((line, i) => (
                <li key={`${line.name}-${i}`}>
                  <span className="cart-name">{line.name}</span>
                  <span className="muted data">
                    × {line.quantity} · {line.price} ₴
                  </span>
                </li>
              ))}
            </ul>
            <dl className="cart-facts">
              <dt>Сума товарів</dt>
              <dd className="data">{cart.products_total} ₴</dd>
              {diagnosis?.gap !== null && diagnosis?.gap !== undefined && (
                <>
                  <dt>До мінімуму не вистачає</dt>
                  <dd className="data">{diagnosis.gap} ₴</dd>
                </>
              )}
              <dt>Доставка</dt>
              <dd className="data">{cart.delivery_type ?? "—"}</dd>
              <dt>Слот</dt>
              <dd className="data">{slot(cart.timeslot_start, cart.timeslot_end)}</dd>
            </dl>
          </>
        )}
      </section>

      {evidence !== null && (
        <section className="panel-block">
          <h2>Що показує застосунок — що повертає сервер</h2>
          <p className="muted uk">За аудитом {evidence.disclosure.observed_at} — кошик того дня; коди ті самі, суми могли змінитися.</p>
          <ul className="plain">
            {evidence.disclosure.app_showed.map((line) => (
              <li key={line}>
                <span className="tag">застосунок</span> {line}
              </li>
            ))}
            {evidence.disclosure.validations.map((v) => (
              <li key={v.code}>
                <span className="tag">сервер</span> <code>{v.code}</code>{" "}
                {v.rendered_by_app ? (
                  <span className="muted">— застосунок показує</span>
                ) : (
                  <span className="tag tag-warn">застосунок не показує</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
