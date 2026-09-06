"""G3 (plan section 12.1.1 step 5, amendment A8/D6): a seeded boundary
generator producing one synthetic/mutated fixture per row of
`config/mutation_matrix.yaml`, wrapped in the existing envelope schema
(`datasets/fixtures/envelope.schema.json`), and registered into
`datasets/fixtures/manifest.json`.

Deterministic by construction (G3-F14): uses a local `random.Random(seed)`
instance, never the global `random` module, so two runs with the same
seed produce byte-identical output regardless of what else has touched
global random state in the same process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = PROJECT_ROOT / "config" / "mutation_matrix.yaml"
MANIFEST_PATH = PROJECT_ROOT / "datasets" / "fixtures" / "manifest.json"
GENERATOR_VERSION = "1.0.0"

# A fixed schema hash for the synthetic wire shape this generator emits —
# not a live `tools/list` hash (this generator produces cart bodies, not
# tool schemas); named so the envelope's `source_schema_hash` field is
# never left as a placeholder.
SYNTHETIC_SCHEMA_HASH = "synthetic-cart-wire-shape-v1"


def _base_cart(rng: random.Random, cart_id: str) -> Dict[str, Any]:
    return {
        "id": cart_id,
        "deliveryType": "NovaPoshta",
        "calculation": {
            "total": 133.89,
            "totalAfterDiscounts": 133.89,
            "subTotal": 133.89,
            "subDiscount": 0,
            "productsTotal": 100.0,
            "delivery": {"total": 33.89},
            "validations": [],
        },
        "shipments": [
            {
                "id": cart_id,
                "companyId": "company-1",
                "branchId": "branch-1",
                "products": [
                    {
                        "productId": f"product-{rng.randint(1, 9999)}",
                        "name": "Synthetic item",
                        "quantity": 1,
                        "price": 100.0,
                        "stock": 10,
                    }
                ],
            }
        ],
    }


def _apply_scenario(
    rng: random.Random, scenario_id: str, cart: Dict[str, Any]
) -> Dict[str, Any]:
    calc = cart["calculation"]

    if scenario_id == "gap_below_threshold":
        calc["productsTotal"] = 100.0
        calc["validations"] = [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ]
    elif scenario_id == "gap_at_threshold_borderline":
        calc["productsTotal"] = 598.99
        calc["validations"] = [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599.00},
            }
        ]
    elif scenario_id == "gap_above_threshold_clears":
        calc["productsTotal"] = 1561.46
        calc["validations"] = []
    elif scenario_id == "money_as_minor_units_string":
        calc["productsTotal"] = "639.65"
    elif scenario_id == "null_delivery_cost":
        calc["delivery"]["total"] = None
    elif scenario_id == "zero_delivery_cost":
        calc["delivery"]["total"] = 0
    elif scenario_id == "unknown_validation_code":
        calc["validations"] = [
            {
                "level": "error",
                "type": "product",
                "message": "product.offer.status.not_available",
                "context": {
                    "productId": cart["shipments"][0]["products"][0]["productId"]
                },
            }
        ]
    elif scenario_id == "unavailable_item_zero_price":
        item = cart["shipments"][0]["products"][0]
        item["price"] = 0
        item["stock"] = 0
        calc["validations"] = [
            {
                "level": "error",
                "type": "product",
                "message": "product.offer.stock.max",
                "context": {"productId": item["productId"]},
            }
        ]
    else:
        raise ValueError(f"unknown scenario id: {scenario_id}")

    return cart


def _load_matrix() -> List[Dict[str, str]]:
    import yaml

    raw = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    scenarios: List[Dict[str, str]] = raw["scenarios"]
    return scenarios


def generate(seed: int) -> Tuple[List[Dict[str, Any]], str]:
    """Returns the list of envelope-wrapped fixtures, one per matrix row,
    in the matrix file's own order — so byte-identical output across runs
    depends only on `seed`, never on filesystem iteration order."""
    rng = random.Random(seed)
    scenarios = _load_matrix()
    generated_at = datetime.now(timezone.utc).isoformat()

    envelopes: List[Dict[str, Any]] = []
    for scenario in scenarios:
        cart_id = f"synthetic-{scenario['id']}"
        cart = _base_cart(rng, cart_id)
        cart = _apply_scenario(rng, scenario["id"], cart)

        envelope = {
            "fixture_id": scenario["id"],
            "origin": scenario["origin"],
            "source_schema_hash": SYNTHETIC_SCHEMA_HASH,
            "generator_version": GENERATOR_VERSION,
            "seed": seed,
            "transformations": [scenario["description"]],
            "expected_outcome": {},
            "payload": cart,
        }
        envelopes.append(envelope)

    return envelopes, generated_at


def _write_fixtures(envelopes: List[Dict[str, Any]]) -> None:
    for envelope in envelopes:
        out_dir = PROJECT_ROOT / "datasets" / "fixtures" / envelope["origin"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{envelope['fixture_id']}.json"
        out_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _update_manifest(
    envelopes: List[Dict[str, Any]], seed: int, generated_at: str
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["schema_hash"] = SYNTHETIC_SCHEMA_HASH
    manifest["generator_version"] = GENERATOR_VERSION
    manifest["generated_at"] = generated_at
    manifest["seed"] = seed
    manifest["fixtures"] = [
        {
            "fixture_id": e["fixture_id"],
            "origin": e["origin"],
            "path": f"datasets/fixtures/{e['origin']}/{e['fixture_id']}.json",
        }
        for e in envelopes
    ]
    manifest["coverage"]["DR"] = sorted(
        {t for e in envelopes for t in e["transformations"]}
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def content_hash(envelopes: List[Dict[str, Any]]) -> str:
    """Used by the determinism test: a hash over the generated envelopes'
    JSON, excluding `expected_outcome`'s timestamp-free content — the
    envelopes themselves carry no wall-clock field, so two runs with the
    same seed hash identically."""
    canonical = json.dumps(envelopes, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)

    envelopes, generated_at = generate(args.seed)
    _write_fixtures(envelopes)
    _update_manifest(envelopes, args.seed, generated_at)
    print(f"wrote {len(envelopes)} fixtures, seed={args.seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
