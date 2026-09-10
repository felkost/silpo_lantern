// G10: an append-only log of the nodes the stream reported completing.
// No pre-drawn checklist and no "pending" rows: a compensation round
// enters write_guard directly and retry returns to diagnose, so a fixed
// list would promise work the run does not do. The only forward-looking
// element is one "working" line while the stream is open, which claims
// nothing about what comes next.

import { IO_LABEL, type StageRow } from "../stages";
import { Help } from "./Help";

interface Props {
  rows: StageRow[];
  streaming: boolean;
}

export function StageFeed({ rows, streaming }: Props) {
  // The last frame carries the session's cumulative spend (D90): shown as
  // spent, beside the project's ceiling -- never as what remains.
  const spend = [...rows].reverse().find((r) => r.usage)?.usage;
  return (
    <section className="panel-block" aria-labelledby="stage-heading">
      <h2 id="stage-heading">Observed nodes</h2>
      <Help>
        Журнал кроків, які агент справді виконав у цій сесії, у порядку надходження.
        MCP — читання чи запис кошика через сервер Сільпо; LLM — виклик мовної моделі;
        DB — база даних; pure — обчислення без мережі. «working…» означає, що потік
        відкритий і сервер ще працює. Рядок «Spent» — токени й долари цієї сесії за
        даними провайдера; стеля — рішення проєкту, а не залишок.
      </Help>
      {rows.length === 0 && !streaming && (
        <p className="muted">Nothing observed in this session yet.</p>
      )}
      <ol className="stage-list">
        {rows.map((row, index) => (
          <li key={index} data-testid="stage-row" className="stage-row">
            <code>{row.node}</code>
            <span className={`io io-${row.io.replace("+", "-")}`}>{IO_LABEL[row.io] ?? row.io}</span>
          </li>
        ))}
      </ol>
      {streaming && (
        <p className="muted working" aria-live="polite">
          working…
        </p>
      )}
      {spend && (
        <p className="muted data" data-testid="spend">
          Spent by this session: {spend.tokens} tokens · ${spend.cost_usd.toFixed(4)} · project
          ceiling ${spend.ceiling_usd}
        </p>
      )}
    </section>
  );
}
