// G10 (D-G10-03): the panel is organised by CLAIM, not by data source. A
// panel grouped by provenance is a debug dump; one grouped by what a field
// proves is an argument a jury can check. Four live claims here; the
// fifth (reproducibility) is MeasuredEarlier, kept apart so a session
// figure is never read as a project figure.
//
// English by decision (A-G10-02): this is a technical surface. Every
// value shown is one the wire carried; anything not seen in this session
// says so rather than rendering as absent.

import type {
  Candidate,
  ConsentAckResponse,
  DiagnosisEvent,
  EvidenceResponse,
  ReceiptEvent,
} from "../types";
import { Help } from "./Help";

interface Props {
  diagnosis: DiagnosisEvent | null;
  candidates: Candidate[];
  consent: ConsentAckResponse | null;
  receipts: ReceiptEvent[];
  refusal: string | null;
  evidence: EvidenceResponse | null;
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

export function ClaimPanel({ diagnosis, candidates, consent, receipts, refusal, evidence }: Props) {
  return (
    <section className="panel-block" aria-labelledby="claims-heading">
      <h2 id="claims-heading">What this run shows</h2>
      <Help>
        Чотири твердження проєкту про те, як працює система; під кожним — дані з
        поточної сесії, які його доводять. Назви полів (args_hash, products_total)
        навмисно ті самі, що в коді, щоб їх можна було звірити.
      </Help>

      <details open data-testid="claim-disclosure">
        <summary>The server returns more than the app shows</summary>
        <p className="muted uk">
          Доводить: сервер повертає разом із кошиком усі результати перевірок, з
          рівнями, а застосунок Сільпо показує не всі. «unknown code» — коду немає в
          реєстрі правил, і система свідомо його не тлумачить. Рядок «Audited» —
          перевірене раніше спостереження: який із результатів застосунок показує, а
          який ні.
        </p>
        {diagnosis === null ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain">
            {grouped(diagnosis.validations).map(([v, count]) => (
              <li key={v.code}>
                <code>{v.code}</code> <span className="tag">{v.level}</span>
                {count > 1 && <span className="muted"> × {count}</span>}
                {v.is_known === false && <span className="tag tag-warn">unknown code</span>}
              </li>
            ))}
          </ul>
        )}
        {evidence !== null && (
          <p className="muted">
            Audited {evidence.disclosure.observed_at}:{" "}
            {evidence.disclosure.validations.map((v) => (
              <span key={v.code}>
                <code>{v.code}</code> {v.rendered_by_app ? "rendered by the app" : "NOT rendered by the app"}
                {"; "}
              </span>
            ))}
          </p>
        )}
      </details>

      <details open data-testid="claim-arithmetic">
        <summary>Money is computed by code, never by the model</summary>
        <p className="muted uk">
          Доводить: вартість товарів (products_total) узято з кошика, поріг — з даних
          самої перевірки, недостача (gap) — їхня різниця, порахована кодом. Ціна
          кожного варіанта — з відповіді інструмента пошуку, названого поруч. Речення
          моделі на картці лише пояснює, а не рахує.
        </p>
        {diagnosis === null ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <p>
            products_total <code>{diagnosis.products_total ?? "—"}</code> → gap{" "}
            <code>{diagnosis.gap ?? "—"}</code> (threshold from{" "}
            <code>{diagnosis.threshold_source}</code>)
          </p>
        )}
        {candidates.length > 0 && (
          <ul className="plain">
            {candidates.map((c) => (
              <li key={c.action_id}>
                typed delta <code>{c.expected_delta}</code> from{" "}
                {(c.evidence ?? []).map((e) => (
                  <span key={e.captured_at}>
                    <code>{e.price}</code> via <code>{e.source_tool}</code>
                  </span>
                ))}
                ; the model's sentence is shown on the card, independently.
              </li>
            ))}
          </ul>
        )}
      </details>

      <details open data-testid="claim-consent">
        <summary>Nothing is written without item-bound consent</summary>
        <p className="muted uk">
          Доводить: «записується» — у кошик клієнта на сервері Сільпо. Згода прив'язана
          до конкретної дії контрольною сумою дії (args_hash: кошик, товар, кількість) і
          контрольною сумою стану кошика (state_hash), з терміном дії. Якщо вартовий
          запису відмовив — його відмова показана його власними словами.
        </p>
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
        <p className="muted uk">
          Доводить: сервер Сільпо відповідає на запис лише «успішно», без сум, тому
          після запису кошик перечитується окремо. «verified» — зміна з перечитування
          збіглася з очікуваною; «unverified» — не збіглася або перечитати не вдалося.
        </p>
        {receipts.length === 0 ? (
          <p className="muted">{NOT_OBSERVED}</p>
        ) : (
          <ul className="plain">
            {receipts.map((r, i) => (
              <li key={i}>
                expected <code>{r.expected_delta ?? "—"}</code>, read back{" "}
                <code>{r.actual_delta ?? "—"}</code> →{" "}
                <span className={`tag ${r.verified ? "tag-ok" : "tag-warn"}`}>
                  {r.verified ? "verified" : "unverified"}
                </span>
                {r.blocker_cleared ? " blocker cleared" : ` remaining gap ${r.remaining_gap ?? "—"}`}
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
