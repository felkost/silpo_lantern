"""G3-F14: the same seed produces byte-identical output across two
separate runs — a local `random.Random(seed)` instance, never the global
`random` module, so global state left over from another test cannot make
this generator order-dependent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.generate_boundary_fixtures import content_hash, generate  # noqa: E402


def test_same_seed_produces_identical_output() -> None:
    envelopes_a, _ = generate(seed=20260907)
    envelopes_b, _ = generate(seed=20260907)

    assert content_hash(envelopes_a) == content_hash(envelopes_b)


def test_different_seed_still_matches_on_deterministic_scenario_coverage() -> None:
    """Scenarios that don't consume `rng` (most of the matrix) are
    seed-invariant by construction; this pins that only the
    randomness-dependent fields (product ids) could differ, and even then
    only when a scenario actually draws from `rng`."""
    envelopes_a, _ = generate(seed=1)
    envelopes_b, _ = generate(seed=2)

    ids_a = {e["fixture_id"] for e in envelopes_a}
    ids_b = {e["fixture_id"] for e in envelopes_b}
    assert ids_a == ids_b  # same scenario coverage regardless of seed
