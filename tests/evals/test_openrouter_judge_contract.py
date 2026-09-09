"""T18 (G9 spec, D-G9-03): `OpenRouterJudge` implements `DeepEvalBaseLLM`'s
four abstract methods (`generate`, `a_generate`, `get_model_name`,
`load_model`) against the project's existing OpenRouter-bound
`ChatOpenAI` pattern (`graph/llm_adapter.py`'s `build_eval_judge_llm`),
never a second HTTP client. Offline throughout: the underlying LLM is a
fake with a recorded response, no live network call.
"""

from deepeval.models.base_model import DeepEvalBaseLLM

from src.lantern.evals.openrouter_judge import OpenRouterJudge


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatModel:
    """Duck-typed like `langchain_openai.ChatOpenAI` -- `.invoke` and
    `.ainvoke`, both returning an object with `.content`."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.invoke_calls = []
        self.ainvoke_calls = []

    def invoke(self, prompt: str):
        self.invoke_calls.append(prompt)
        return _FakeMessage(self.response_text)

    async def ainvoke(self, prompt: str):
        self.ainvoke_calls.append(prompt)
        return _FakeMessage(self.response_text)


def test_openrouter_judge_is_a_deepeval_base_llm() -> None:
    judge = OpenRouterJudge(model="x-ai/grok-4.6", client=_FakeChatModel("x"))
    assert isinstance(judge, DeepEvalBaseLLM)


def test_get_model_name_returns_the_configured_model() -> None:
    judge = OpenRouterJudge(model="x-ai/grok-4.6", client=_FakeChatModel("x"))
    assert judge.get_model_name() == "x-ai/grok-4.6"


def test_load_model_returns_the_wrapped_client() -> None:
    client = _FakeChatModel("x")
    judge = OpenRouterJudge(model="x-ai/grok-4.6", client=client)
    assert judge.load_model() is client


def test_generate_returns_the_underlying_response_text() -> None:
    client = _FakeChatModel("scored: 4/5")
    judge = OpenRouterJudge(model="x-ai/grok-4.6", client=client)

    result = judge.generate("score this response")

    assert result == "scored: 4/5"
    assert client.invoke_calls == ["score this response"]


async def test_a_generate_returns_the_same_content_as_generate() -> None:
    """Sync and async paths must agree -- GEval's `async_mode` toggles
    which one runs, and a divergence between them would make the judge's
    score depend on an implementation detail invisible to the caller."""
    client = _FakeChatModel("scored: 4/5")
    judge = OpenRouterJudge(model="x-ai/grok-4.6", client=client)

    sync_result = judge.generate("score this response")
    async_result = await judge.a_generate("score this response")

    assert sync_result == async_result == "scored: 4/5"
    assert client.ainvoke_calls == ["score this response"]
