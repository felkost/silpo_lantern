// A Ukrainian explanation under an English technical heading (A-G10-02:
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
      <p>{children}</p>
    </details>
  );
}
