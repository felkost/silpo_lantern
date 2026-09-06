"""G3-F15: an independent re-derivation of the DR-03 gap, structurally
separate from `src/lantern/domain/diagnosis.py` — it reads the raw
validation `context` directly and never constructs a `Cart` or
`Diagnosis`, so a copy-paste of the implementation would not pass as an
"independent" oracle (a review pass alone would not catch that; the
structural difference is what makes it a real second check).
"""

from decimal import Decimal
from typing import Any, Mapping, Optional


def oracle_gap(raw_cart: Mapping[str, Any]) -> Optional[Decimal]:
    """Walks the raw wire-shaped cart dict directly: finds the
    `order.cost.min` validation's own `orderCostMin` context value and
    subtracts `calculation.productsTotal`, using only stdlib `Decimal` and
    dict access — no import from `src.lantern.domain` at all."""
    calculation = raw_cart.get("calculation") or {}
    products_total_raw = calculation.get("productsTotal")
    if products_total_raw is None:
        return None
    products_total = Decimal(str(products_total_raw))

    for validation in calculation.get("validations") or []:
        if validation.get("message") == "order.cost.min":
            threshold_raw = (validation.get("context") or {}).get("orderCostMin")
            if threshold_raw is None:
                return None
            threshold = Decimal(str(threshold_raw))
            return threshold - products_total
    return None
