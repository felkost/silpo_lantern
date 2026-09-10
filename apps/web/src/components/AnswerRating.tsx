// G10: a jury member's rating of the answer, 1-5 plus a note. Author's
// decision: session state only, never Neon -- React state IS that, so
// there is no backend and nothing leaves the browser. Button names avoid
// every accessible name the card's tests protect.

import { useState } from "react";

export function AnswerRating() {
  const [score, setScore] = useState<number | null>(null);
  const [note, setNote] = useState("");
  return (
    <section className="panel-block" aria-labelledby="rating-heading">
      <h2 id="rating-heading">Your rating — this browser only</h2>
      <p className="rating-row">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={n === score ? "rate on" : "rate"}
            aria-label={`Rate ${n} of 5`}
            aria-pressed={n === score}
            onClick={() => setScore(n)}
          >
            {n}
          </button>
        ))}
        <span className="muted data" data-testid="rating-value">
          {score === null ? "not rated" : `${score} / 5`}
        </span>
      </p>
      <textarea
        aria-label="Note"
        rows={2}
        placeholder="What would you check next?"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
    </section>
  );
}
