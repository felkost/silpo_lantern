// the panel is organised by CLAIM, not by data source. A
// panel grouped by provenance is a debug dump; one grouped by what a field
// proves is an argument a jury can check. Four live claims here; the
// fifth (reproducibility) is MeasuredEarlier, kept apart so a session
// figure is never read as a project figure.
//
// English by decision: this is a technical surface. Every
// value shown is one the wire carried; anything not seen in this session
// says so rather than rendering as absent.

import type {
  Candidate,
  ConsentAckResponse,
  DiagnosisEvent,
  ReceiptEvent,
} from "../types";
import { translateValidationCode } from "../copy";
import { Help, Terms } from "./Help";

interface Props {
  diagnosis: DiagnosisEvent | null;
  candidates: Candidate[];
  consent: ConsentAckResponse | null;
  receipts: ReceiptEvent[];
  refusal: string | null;
}

const NOT_OBSERVED = "Not observed in this session.";

function grouped<T extends { code: string }>(items: T[]): Array<[T, number]> {
  const groups = new Map<string, [T, number]>();
  for (const item of items) {
    const entry = groups.get(item.code);
    if (entry) {
      entry[1] += 1;
    } else {
      groups.set(item.code, [item, 1]);
    }
  }
  return [...groups.values()];
}

function short(hash: string): string {
  return `${hash.slice(0, 12)}…`;
}

export function ClaimPanel({ diagnosis, candidates, consent, receipts, refusal }: Props) {
  return (
    <section className="panel-block" aria-labelledby="claims-heading">
      <h2 id="claims-heading">What this run shows</h2>
      <Help>
        <p>Чотири твердження проєкту про те, як працює система. Під кожним — дані з цієї
        сесії, які його доводять. Назви полів — ті самі, що в коді, щоб їх можна було
        звірити.</p>
      </Help>

      <details open data-testid="claim-disclosure">
        <summary>The server returns more than the app shows</summary>
        <div className="muted uk">
          <p>Доводить:</p>
          <Terms
            items={[
              [
                "Результати перевірок",
                "усе, що сервер повернув разом із кошиком, з рівнем кожного. Застосунок Сільпо показує не всі.",
              ],
              ["unknown code", "коду немає в реєстрі правил; система свідомо його не тлумачить."],
            ]}
          />
        </div>
        {diagnosis === null ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain">
            {grouped(diagnosis.validations).map(([v, count]) => (
              <li key={v.code} className="validation-row">
                <div>
                  <code>{v.code}</code> <span className="tag">{v.level}</span>
                  {count > 1 && <span className="muted"> × {count}</span>}
                  {v.is_known === false && <span className="tag tag-warn">unknown code</span>}
                </div>
                {/* The code is what the server returned and what the jury can
                    check against the registry; the Ukrainian line is the same
                    sentence the Customer's card shows for it. */}
                <div className="muted uk">{translateValidationCode(v)}</div>
              </li>
            ))}
          </ul>
        )}
      </details>

      <details open data-testid="claim-arithmetic">
        <summary>Money is computed by code, never by the model</summary>
        <div className="muted uk">
          <p>Доводить:</p>
          <Terms
            items={[
              ["products_total", "вартість товарів, з кошика."],
              ["threshold", "поріг мінімальної суми, з даних самої перевірки."],
              ["gap", "недостача: різниця між ними, порахована кодом."],
              ["typed delta", "ціна варіанта — з відповіді інструмента пошуку, названого поруч."],
              ["Речення моделі", "на картці лише пояснює, а не рахує."],
            ]}
          />
        </div>
        {diagnosis === null ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain rows">
            <li>
              <code>products_total</code> <span className="data">{diagnosis.products_total ?? "—"}</span>
            </li>
            <li>
              <code>threshold</code> <span className="data">from {diagnosis.threshold_source}</span>
            </li>
            <li>
              <code>gap</code> <span className="data">{diagnosis.gap ?? "—"}</span>
            </li>
          </ul>
        )}
        {candidates.length > 0 && (
          <ul className="plain rows">
            {candidates.map((c) => (
              <li key={c.action_id}>
                <code>typed delta</code>{" "}
                <span className="data">
                  {c.expected_delta}
                  {(c.evidence ?? []).map((e) => (
                    <span key={e.captured_at}>
                      {" "}= {e.price} via {e.source_tool}
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </details>

      <details open data-testid="claim-consent">
        <summary>Nothing is written without item-bound consent</summary>
        <div className="muted uk">
          <p>Доводить:</p>
          <Terms
            items={[
              ["Записується", "у кошик клієнта на сервері Сільпо."],
              ["args_hash", "контрольна сума дії: кошик, товар, кількість."],
              ["state_hash", "контрольна сума стану кошика на момент згоди."],
              ["expires", "термін дії згоди."],
              ["guard refused", "вартовий запису відмовив; причина — його власними словами."],
            ]}
          />
        </div>
        {candidates.length === 0 && consent === null ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain">
            {candidates.map((c) => (
              <li key={c.action_id}>
                candidate <code>{c.tool_name}</code> args_hash <code>{short(c.args_hash ?? "")}</code>
              </li>
            ))}
            {consent !== null && (
              <li>
                consent recorded: args_hash <code>{short(consent.args_hash)}</code>, state_hash{" "}
                <code>{short(consent.state_hash)}</code>, expires <code>{consent.expires_at.slice(0, 19)}Z</code>
              </li>
            )}
            {refusal !== null && (
              <li>
                guard refused (its own word): <code>{refusal}</code>
              </li>
            )}
          </ul>
        )}
      </details>

      <details open data-testid="claim-readback">
        <summary>Success is never asserted, only read back</summary>
        <div className="muted uk">
          <p>Доводить:</p>
          <Terms
            items={[
              [
                "Чому перечитуємо",
                "сервер Сільпо відповідає на запис лише «успішно», без сум; тому кошик читається ще раз, окремо.",
              ],
              ["verified", "зміна з перечитування збіглася з очікуваною."],
              ["unverified", "не збіглася або перечитати не вдалося."],
            ]}
          />
        </div>
        {receipts.length === 0 ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain">
            {receipts.map((r, i) => (
              <li key={i}>
                <code>expected</code> <span className="data">{r.expected_delta ?? "—"}</span>
                {" · "}
                <code>read back</code> <span className="data">{r.actual_delta ?? "—"}</span>
                {" "}
                <span className={`tag ${r.verified ? "tag-ok" : "tag-warn"}`}>
                  {r.verified ? "verified" : "unverified"}
                </span>{" "}
                <span className="muted">
                  {r.blocker_cleared ? "blocker cleared" : `remaining gap ${r.remaining_gap ?? "—"}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
