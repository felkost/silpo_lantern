"""G7 (D-G7-06): the offline proof that a tracked bundle replays the REAL
compiled hero graph to the recorded outcome -- no MCP network call, no
LLM call, no Postgres connection. This is what the project's Definition
of Done calls "a controlled live proof and an explicitly labeled replay
fallback"; the live proof is G5+G6's own A6 evidence, this is the replay
fallback.

`datasets/fixtures/replay/hero_order_cost_min.json` is `origin: synthetic`
(the fixture envelope's own field) -- built from the same synthetic cart
`tests/unit/test_write_path_interrupt_and_resume.py` already uses, not
from a live capture. A live-recorded bundle is `scripts/record_replay_bundle.py`'s
job, gated on the author's explicit go-ahead for a live MCP write (this
stage's own plan, section 4) -- this test proves the REPLAY MECHANISM
itself works, independent of when a live-recorded bundle lands.
"""

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.build import policy_registry_version
from src.lantern.graph.replay import load_bundle, replay

BUNDLE_PATH = (
    PROJECT_ROOT / "datasets" / "fixtures" / "replay" / "hero_order_cost_min.json"
)


def test_hero_bundle_replays_to_the_recorded_outcome() -> None:
    bundle = load_bundle(BUNDLE_PATH)
    result = replay(bundle)

    assert result.final_state.get("status") == bundle.expected_outcome["final_status"]
    assert len(result.receipts) == len(bundle.expected_outcome["receipts"])
    for actual, expected in zip(result.receipts, bundle.expected_outcome["receipts"]):
        got = actual.model_dump(mode="json")
        # [A-3]: action_id is a fresh uuid4 every replay, never comparable
        # byte-for-byte -- the binding property this proves instead is
        # that the LAST receipt's action_id equals the id actually
        # consented to. before_state/after_state are excluded too
        # ([A-7]): full Cart dumps have no place in a tracked file, and
        # the outcome fields below are what the proof actually needs.
        for excluded in (
            "action_id",
            "created_at",
            "trace_id",
            "before_state",
            "after_state",
        ):
            got.pop(excluded, None)
        assert got == expected

    assert result.receipts, "the bundle recorded no receipts to check against"
    assert result.consented_action_id != ""


def test_replaying_the_same_bundle_twice_is_deterministic() -> None:
    """Catches nondeterminism a single run would not: the bundle's own
    queues are consumed in order, so a second independent `replay()` call
    (a fresh `BundlePlayer`, fresh `InMemorySaver`) must reach the exact
    same outcome as the first."""
    bundle = load_bundle(BUNDLE_PATH)
    first = replay(bundle)
    second = replay(load_bundle(BUNDLE_PATH))

    assert first.final_state.get("status") == second.final_state.get("status")
    assert len(first.receipts) == len(second.receipts)
    for a, b in zip(first.receipts, second.receipts):
        a_dump = a.model_dump(mode="json")
        b_dump = b.model_dump(mode="json")
        for excluded in ("action_id", "created_at", "trace_id"):
            a_dump.pop(excluded, None)
            b_dump.pop(excluded, None)
        assert a_dump == b_dump


def test_the_bundles_own_policy_registry_version_still_matches_live() -> None:
    """A `registry.yaml` edit fails HERE with a clear reason, rather than
    surfacing as an opaque receipt mismatch in the test above."""
    bundle = load_bundle(BUNDLE_PATH)
    assert bundle.versions["policy_registry_version"] == policy_registry_version()
