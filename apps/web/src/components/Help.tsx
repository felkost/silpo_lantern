// A Ukrainian explanation under an English technical heading (the rule:
// identifiers match the code; the words that explain them are for the
// reader). Native <details>, closed by default, no JS.

import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
}

export function Help({ children }: Props) {
  return (
    <details className="help">
      <summary>Що це?</summary>
      <div className="help-body">{children}</div>
    </details>
  );
}

/** One line per term: the term in italics, then a short sentence. Used for
 * every «Що це?» and «Доводить» block so they all read the same way. */
export function Terms({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="terms">
      {items.map(([term, text]) => (
        <p key={term}>
          <i>{term}</i> — {text}
        </p>
      ))}
    </div>
  );
}
