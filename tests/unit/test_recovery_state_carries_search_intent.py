"""Found while wiring the graph nodes together: `collect_options` (§4.2
step 5) needs the planner's `SearchIntent` — search terms, which
`build_action_proposals` needs downstream. Nodes only communicate through
`RecoveryState`, so the planner's output needs a field to land in.

`SearchIntent.quantity_hint` was removed (`planner_v2.md`) — quantity
is arithmetic on the diagnosed gap, never a model output; this test no
longer exercises that field.
"""

from datetime import datetime, timezone

from src.lantern.graph.schemas import SearchIntent
from src.lantern.graph.state import new_recovery_state


def test_a_fresh_state_has_no_search_intent_yet() -> None:
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )
    assert state["search_intent"] is None


def test_search_intent_can_be_set_and_read_back() -> None:
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )
    intent = SearchIntent(search_terms=["молоко"])
    state["search_intent"] = intent
    assert state["search_intent"].search_terms == ["молоко"]
