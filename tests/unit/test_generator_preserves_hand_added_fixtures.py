"""`generate_boundary_fixtures.py`'s `_update_manifest` replaced
`manifest["fixtures"]` wholesale with only the envelopes IT generated --
correct when the generator was written and every fixture came from the
matrix, silently destructive now that the manifest also carries recorded
captures (`cart_blocked_order_cost_min`, `cart_multi_item_diverse`), the
replay BUNDLE (`replay_hero_order_cost_min`), and the golden-case
fixtures added by hand.

Running the generator to add three new matrix rows would therefore have
dropped seven of fifteen entries, and nothing in the gate would have
noticed until a golden case failed to resolve its own fixture.
"""

import json

from scripts.generate_boundary_fixtures import _update_manifest, MANIFEST_PATH


def test_a_hand_added_fixture_entry_survives_regeneration(
    monkeypatch, tmp_path
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "coverage": {"DR": [], "GD": [], "RG": [], "replay": []},
                "fixtures": [
                    {
                        "fixture_id": "generated_one",
                        "origin": "synthetic",
                        "path": "datasets/fixtures/synthetic/generated_one.json",
                    },
                    {
                        "fixture_id": "replay_hero_order_cost_min",
                        "origin": "synthetic",
                        "path": "datasets/fixtures/replay/hero_order_cost_min.json",
                        "provenance": "hand-added: the replay bundle",
                    },
                ],
                "generated_at": "x",
                "generator_version": "1.0.0",
                "schema_hash": "x",
                "seed": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.generate_boundary_fixtures.MANIFEST_PATH", manifest_path
    )

    envelopes = [
        {
            "fixture_id": "generated_one",
            "origin": "synthetic",
            "transformations": ["regenerated"],
        }
    ]
    _update_manifest(envelopes, seed=1, generated_at="y")

    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = {entry["fixture_id"] for entry in written["fixtures"]}

    assert "generated_one" in ids, "the generated entry must still be written"
    assert "replay_hero_order_cost_min" in ids, (
        "a hand-added entry the generator does not produce was dropped -- "
        "regeneration must merge, not replace"
    )


def test_a_hand_added_entry_keeps_its_provenance(monkeypatch, tmp_path) -> None:
    """Merging must preserve the whole entry, not just its id -- the
    `provenance` field is the only record of where a recorded capture
    came from."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "coverage": {"DR": []},
                "fixtures": [
                    {
                        "fixture_id": "cart_multi_item_diverse",
                        "origin": "recorded",
                        "path": (
                            "datasets/fixtures/sanitized/"
                            "cart_multi_item_diverse.json"
                        ),
                        "provenance": "live capture 2026-09-06",
                    }
                ],
                "generated_at": "x",
                "generator_version": "1.0.0",
                "schema_hash": "x",
                "seed": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.generate_boundary_fixtures.MANIFEST_PATH", manifest_path
    )

    _update_manifest([], seed=1, generated_at="y")

    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    kept = [
        e for e in written["fixtures"] if e["fixture_id"] == "cart_multi_item_diverse"
    ]
    assert kept, "the recorded capture's entry was dropped"
    assert kept[0]["provenance"] == "live capture 2026-09-06"


def test_real_manifest_carries_entries_the_generator_does_not_produce() -> None:
    """Pins WHY the merge matters against the real repository, not just a
    synthetic manifest: if this ever returns empty, the generator's own
    output covers everything and the merge is dead weight."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    import yaml
    from scripts.generate_boundary_fixtures import MATRIX_PATH

    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    generated_ids = {s["id"] for s in matrix["scenarios"]}
    manifest_ids = {e["fixture_id"] for e in manifest["fixtures"]}

    assert manifest_ids - generated_ids, (
        "no hand-added fixtures found -- the merge behaviour this test "
        "protects would be unnecessary"
    )
