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

/** A two-column table: the term on the left, one short sentence on the
 * right, both columns aligned. Used for every «Що це?» and «Доводить»
 * block so they all read the same way. */
export function Terms({ items }: { items: Array<[string, string]> }) {
  return (
    <table className="terms">
      <tbody>
        {items.map(([term, text]) => (
          <tr key={term}>
            <th scope="row">{term}</th>
            <td>{text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
