// The cart column (2026-09-11, the author): the starting state and its
// history, as the server returned it. A jury cannot be shown the Silpo
// app itself, so the console shows the cart -- lines, total, minimum,
// slot -- once at the read, and again as each read-back saw it, with the
// changed line marked and the totals side by side. Every state is
// labelled with the step of the guest card it belongs to. Guest-facing
// Ukrainian. Product names are allowed; nothing here identifies the guest.

import { Help, Terms } from "./Help";
import type { CartView } from "../types";

export interface CartState {
  /** Which step of the card produced it: the read, or a read-back. */
  step: "read" | "readback";
  cart: CartView;
  /** The receipt's own delta, for the read-back states. */
  delta: string | null;
}

interface Props {
  states: CartState[];
  gap: string | null;
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

function key(line: { name: string; quantity: string }): string {
  return `${line.name}|${line.quantity}`;
}

export function CartColumn({ states, gap }: Props) {
  return (
    <aside className="cart-column" aria-label="Стан кошика" data-testid="cart-column">
      <p className="eyebrow">Кошик</p>
      <section className="panel-block">
        <h2>Стан кошика</h2>
        <Help>
          <p>Кошик так, як його бачить сервер Сільпо.</p>
          <Terms
            items={[
              ["Перший стан", "при читанні кошика."],
              ["Наступні", "після кожного запису, перечитані окремо."],
              ["Підсвічений рядок", "той, що додав запис."],
              ["Застосунок Сільпо", "в кадрі не показуємо."],
            ]}
          />
        </Help>
        {states.length === 0 && <p className="muted">Кошик ще не прочитано.</p>}
        {states.map((state, index) => {
          const previous = index > 0 ? new Set(states[index - 1].cart.lines.map(key)) : null;
          return (
            <div className="cart-state" data-testid="cart-state" key={index}>
              <h3>
                Стан {index + 1} ·{" "}
                {state.step === "read" ? "при читанні, до дії" : "після запису, перечитано"}
              </h3>
              <ul className="plain cart-lines">
                {state.cart.lines.map((line, i) => {
                  const added = previous !== null && !previous.has(key(line));
                  return (
                    <li key={`${line.name}-${i}`} className={added ? "cart-added" : undefined}>
                      <span className="cart-name">{line.name}</span>
                      {/* Receipt layout: quantity × unit price, one line, never wrapped. */}
                      <span className="cart-amount data">
                        {line.quantity} × {line.price} ₴
                      </span>
                    </li>
                  );
                })}
              </ul>
              <dl className="cart-facts">
                <dt>Сума товарів</dt>
                <dd className="data">
                  {state.cart.products_total} ₴
                  {state.delta !== null && (
                    <span className="muted"> ({state.delta.startsWith("-") ? "" : "+"}{state.delta})</span>
                  )}
                </dd>
                {state.step === "read" && gap !== null && (
                  <>
                    <dt>До мінімуму не вистачає</dt>
                    <dd className="data">{gap} ₴</dd>
                  </>
                )}
                {index === 0 && (
                  <>
                    <dt>Доставка</dt>
                    <dd className="data">{state.cart.delivery_type ?? "—"}</dd>
                    <dt>Слот</dt>
                    <dd className="data">{slot(state.cart.timeslot_start, state.cart.timeslot_end)}</dd>
                  </>
                )}
              </dl>
            </div>
          );
        })}
      </section>

    </aside>
  );
}
