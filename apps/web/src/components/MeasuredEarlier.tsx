// G10 (claim 5): the metrics, each with its n, its 95% Wilson interval
// and its caveat -- and beside them the command that regenerates the
// file they came from. Fetched only when asked (nothing fetches on mount),
// and headed with its date and population so a jury never reads a project
// figure as a session figure, or the reverse.

import { useState } from "react";

import { getEvidence } from "../api";
import { METRIC_UK } from "../copy";
import type { EvidenceResponse } from "../types";
import { Help } from "./Help";

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
        Вісім показників проєкту, виміряних раніше на збережених записах 18 прогонів —
        не в цій сесії. n — розмір вибірки (33 — кількість записів у кошик за ці
        прогони), у дужках — 95% інтервал за методом Вілсона. Під кожним показником —
        його значення українською і застереження з файла metrics.json; команда поруч
        відтворює цей файл із нуля.
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
          <p className="muted">
            Population <code>{evidence.population}</code>, generated{" "}
            <code>{evidence.generated_at.slice(0, 10)}</code>. Regenerate:{" "}
            <code className="select-all">{evidence.regenerate}</code>
          </p>
          <ul className="plain metrics">
            {evidence.metrics.map((m) => (
              <li key={m.name}>
                <div>
                  <code>{m.name}</code>{" "}
                  <strong className="data">{m.value === null ? "N/A" : m.value.toFixed(3)}</strong>{" "}
                  <span className="muted data">
                    n = {m.n}
                    {m.interval !== null && ` · 95% [${m.interval[0].toFixed(2)}, ${m.interval[1].toFixed(2)}]`}
                  </span>
                </div>
                {METRIC_UK[m.name] && (
                  <div className="uk">
                    <b>{METRIC_UK[m.name][0]}</b> — {METRIC_UK[m.name][1]}
                  </div>
                )}
                <div className="muted caveat">{m.caveat}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
