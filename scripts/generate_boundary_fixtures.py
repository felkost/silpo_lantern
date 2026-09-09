"""A seeded boundary generator producing one synthetic/mutated fixture per
row of `config/mutation_matrix.yaml`, wrapped in the existing envelope
schema (`datasets/fixtures/envelope.schema.json`), and registered into
`datasets/fixtures/manifest.json`.

Deterministic by construction: uses a local `random.Random(seed)` instance,
never the global `random` module, so two runs with the same seed produce
byte-identical output regardless of what else has touched global random
state in the same process.
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
        # G9: every seeded cart carries a timeslot. Without one,
        # `collect_and_gate_node` aborts with "cart has no active
        # timeslot" -- product availability is slot-bound -- so a
        # timeslot-less fixture is structurally incapable of driving the
        # graph past the Evidence Gate, and every seeded fixture was.
        # Fixed while synthesizing GD-02/03/04's replay bundles, which
        # need exactly that path to complete. No address is added: the
        # coordinate ban on tracked datasets stands, and
        # `compare_channels_node` degrades to a documented no-op without
        # one.
        "timeslot": {
            "start": "2026-09-08T10:00:00+00:00",
            "end": "2026-09-08T12:00:00+00:00",
        },
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
    elif scenario_id == "gap_needs_two_items":
        # 599 - 100 = 499 to close; no single realistic grocery item
        # covers that, so the plan must combine two.
        calc["productsTotal"] = 100.0
        calc["validations"] = [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ]
    elif scenario_id == "gap_has_several_viable_plans":
        # 599 - 560 = 39 to close: an ordinary grocery price range, so
        # several candidates each close it alone and ranking decides.
        # The line item carries the whole total: `canonical_diff` asserts
        # the line-item sum and `productsTotal` agree, so a cart whose
        # declared total does not match its own items fails the write
        # path's read-back with an invariant violation.
        calc["productsTotal"] = 560.0
        cart["shipments"][0]["products"][0]["price"] = 560.0
        calc["validations"] = [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ]
    elif scenario_id == "weighted_item_in_cart":
        item = cart["shipments"][0]["products"][0]
        item["weighted"] = True
        # A weighted line's quantity is a mass in kilograms, not a count
        # -- 0.4 kg at 250.00/kg. The step is what a valid quantity must
        # be a multiple of, and it is fractional too.
        item["quantity"] = 0.4
        item["price"] = 250.0
        item["addToBasketStep"] = 0.1
        calc["productsTotal"] = 100.0
        calc["validations"] = [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
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
    # G9: MERGE, never replace. The manifest also carries entries this
    # generator does not produce -- recorded/sanitized live captures, the
    # replay BUNDLE, and the golden-case fixtures added by hand -- and
    # replacing the list wholesale silently dropped all of them. A
    # regenerated entry overwrites its own id; everything else is kept
    # exactly as it was, `provenance` included.
    generated_entries = {
        e["fixture_id"]: {
            "fixture_id": e["fixture_id"],
            "origin": e["origin"],
            "path": f"datasets/fixtures/{e['origin']}/{e['fixture_id']}.json",
        }
        for e in envelopes
    }
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for existing in manifest.get("fixtures", []):
        fixture_id = existing["fixture_id"]
        merged.append(generated_entries.get(fixture_id, existing))
        seen.add(fixture_id)
    for fixture_id, entry in generated_entries.items():
        if fixture_id not in seen:
            merged.append(entry)
    manifest["fixtures"] = merged
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
