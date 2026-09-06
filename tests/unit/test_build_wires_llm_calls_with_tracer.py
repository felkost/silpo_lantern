"""Closing this project's own Definition of Done requirement:
"server/release/schema hash and app/prompt/policy/model versions appear in
the trace."
`build_recovery_graph` wraps the caller-supplied `planner_call`/
`explainer_call` with `traced_llm_call` before handing them to the node
factories — the version tuple (schema_hash, prompt_version, model_id,
policy_registry_version) travels with every LLM call, not just the ones a
developer remembers to annotate by hand.

`policy_registry_version` hashes `registry.yaml`'s own file content rather
than adding a new field to it — the registry/schema files are already
closed and tested; this avoids touching either (`registry.schema.json` has
`additionalProperties: false` at the top level, so a new field would need a
schema change to a stage this project is not the owner of extending).
"""

from src.lantern.graph.build import policy_registry_version


def test_policy_registry_version_is_a_stable_short_hash() -> None:
    v1 = policy_registry_version()
    v2 = policy_registry_version()
    assert v1 == v2
    assert len(v1) == 12
    assert all(c in "0123456789abcdef" for c in v1)
