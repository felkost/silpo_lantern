"""the DeepEval judge wrapper. Implements `DeepEvalBaseLLM`'s
four abstract methods (`generate`, `a_generate`, `get_model_name`,
`load_model`) against the project's existing OpenRouter-bound
`ChatOpenAI` pattern (`graph/llm_adapter.py`'s `build_eval_judge_llm`) --
a fixed path and class name (not "or equivalent"), so this is the ONE
place a judge model is constructed, never a second HTTP client the
project's single OpenRouter integration would otherwise drift from.

Layer: application (`tests/unit/test_layering.py`'s `LAYER_OF["evals"]`)
-- it calls the application-layer OpenRouter adapter pattern and
is consumed only from `tests/evals/`.
"""

from typing import Any, Protocol

from deepeval.models.base_model import DeepEvalBaseLLM


class _ChatModelLike(Protocol):
    """Duck-typed: `langchain_openai.ChatOpenAI`'s own shape -- `.invoke`/
    `.ainvoke`, each returning an object with a `.content` string. Not
    imported from `langchain_openai` directly here, so this module stays
    testable against a fake client with no live network dependency."""

    def invoke(self, prompt: str) -> Any: ...  # noqa: E704
    async def ainvoke(self, prompt: str) -> Any: ...  # noqa: E704


class OpenRouterJudge(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
    # `DeepEvalBaseLLM`'s own `__init_subclass__` is untyped in
    # deepeval==4.1.10 -- third-party gap, not this module's own code;
    # same targeted-ignore pattern as memory/checkpointer.py's
    # AsyncPostgresSaver boundary.
    """A DeepEval-compatible LLM backed by an OpenRouter `ChatOpenAI`
    client built the same way `llm_adapter.build_eval_judge_llm` builds
    one for UA-Eval. Constructed with an already-built client (never
    constructs a live one itself) -- the same "inject the boundary, don't
    build it inside" pattern `llm_adapter.py`'s `make_planner_call`/
    `make_explainer_call` already use, so this class stays testable with
    a fake client, entirely offline.
    """

    def __init__(self, *, model: str, client: _ChatModelLike) -> None:
        self._model = model
        self._client = client

    def generate(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        return str(response.content)

    async def a_generate(self, prompt: str) -> str:
        response = await self._client.ainvoke(prompt)
        return str(response.content)

    def get_model_name(self) -> str:
        return self._model

    def load_model(self) -> Any:
        return self._client
