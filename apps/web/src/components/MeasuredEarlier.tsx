// the metrics, each with its n, its 95% Wilson interval
// and its caveat -- and beside them the command that regenerates the
// file they came from. Fetched only when asked (nothing fetches on mount),
// and headed with its date and population so a jury never reads a project
// figure as a session figure, or the reverse.

import { useState } from "react";

import { getEvidence } from "../api";
import { METRIC_UK } from "../copy";
import type { EvidenceResponse } from "../types";
import { Help, Terms } from "./Help";

interface Props {
  evidence: EvidenceResponse | null;
  onLoaded: (evidence: EvidenceResponse) => void;
}

export function MeasuredEarlier({ evidence, onLoaded }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      onLoaded(await getEvidence());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel-block" aria-labelledby="measured-heading" data-testid="measured-earlier">
      <h2 id="measured-heading">Measured earlier — not this session</h2>
      <Help>
        <p>Вісім показників проєкту, виміряних раніше — не в цій сесії.</p>
        <Terms
          items={[
            [
              "Вибірка",
              "збережені записи 18 прогонів; n = 33 — кількість записів у кошик за ці прогони.",
            ],
            ["95% […]", "довірчий інтервал за методом Вілсона."],
            ["Під показником", "його назва й значення українською; нижче — застереження з файла metrics.json."],
            ["Regenerate", "команда, що відтворює цей файл із нуля."],
          ]}
        />
      </Help>
      {evidence === null ? (
        <p>
          <button type="button" onClick={load} disabled={busy}>
            Load measured evidence
          </button>
          {error !== null && <span className="muted"> {error}</span>}
        </p>
      ) : (
        <>
          <Terms
            items={[
              ["Population", `${evidence.population}, generated ${evidence.generated_at.slice(0, 10)}.`],
              ["Regenerate", evidence.regenerate],
            ]}
          />
          <ul className="plain metrics">
            {evidence.metrics.map((m) => (
              <li key={m.name}>
                <div className="metric-head">
                  <code>{m.name}</code>
                  <strong className="data">{m.value === null ? "N/A" : m.value.toFixed(3)}</strong>
                </div>
                <div className="muted data metric-sample">
                  n = {m.n}
                  {m.interval !== null && (
                    <>
                      {" · "}95% [{m.interval[0].toFixed(2)}, {m.interval[1].toFixed(2)}]
                    </>
                  )}
                </div>
                {METRIC_UK[m.name] && (
                  <p className="uk">
                    <i>{METRIC_UK[m.name][0]}</i> — {METRIC_UK[m.name][1]}
                  </p>
                )}
                <div className="muted caveat">{m.caveat}</div>
              </li>
            ))}
          </ul>

          {/* The audited disclosure observation is the one measurement
              behind DisclosureRate, so it sits here with the other
              measured-earlier figures rather than beside the live cart. */}
          <h3 className="measured-sub">Аудит: що показує застосунок — що повертає сервер</h3>
          <Terms
            items={[
              ["застосунок", "результат перевірки, який застосунок Сільпо показує на екрані."],
              ["сервер", "результат, який сервер повертає разом із кошиком."],
              [
                `Аудит ${evidence.disclosure.observed_at}`,
                "перевірене спостереження того дня; коди ті самі, суми могли змінитися.",
              ],
            ]}
          />
          <ul className="plain rows">
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
        </>
      )}
    </section>
  );
}
