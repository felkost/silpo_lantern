"""The production adapter: the real `planner_call`/`explainer_call`
functions `build_recovery_graph` expects, built around structured-output-
bound `Runnable`s. `make_planner_call`/`make_explainer_call` take an
already-built `StructuredLLM` — never constructing a live `ChatOpenAI`
themselves — so both are testable with a fake `.invoke`, entirely offline.
`build_planner_llm`/`build_explainer_llm` are the thin functions that
actually construct a live OpenRouter-bound client; calling them requires a
real `OPENROUTER_API_KEY` and makes a real network connection on first
`.invoke` — this project's first paid LLM call, gated on the author's
explicit go-ahead. Neither is called by this project's own offline gate or
by any automated test.
"""

import json
from contextvars import ContextVar
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    cast,
)

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.lantern.domain.models import ActionProposal
from src.lantern.domain.repeat_accounting import TokenUsage
from src.lantern.graph.schemas import EvalJudgeScore, ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState
from src.lantern.graph.tool_view import (
    PlannerVisibleTool,
    build_planner_tool_view,
    quote_product_text_as_data,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MODELS_PATH = Path(__file__).resolve().parents[3] / "config" / "models.yaml"

# where a live session's token usage lands. `apps/api` binds a
# fresh list per `/events` call, the same ContextVar pattern
# `mcp.session.current_token_storage` uses (measured to reach sync nodes
# through LangGraph); unbound -- scripts, tests, offline fakes -- means
# nobody is counting, and nothing is recorded.
current_usage_log: ContextVar[Optional[List[Tuple[str, TokenUsage]]]] = ContextVar(
    "current_usage_log", default=None
)


def usage_from_response(response: Any) -> TokenUsage:
    """Reads the provider's own usage block off a raw LangChain message.

     A response carrying none records ZEROS, never an estimate: an
     unmeasured call must stay visibly unmeasured rather than contribute a
     guessed number to a cost report. Lived in `scripts/core_e2e_repeats.py`
    ; the live session needed it too."""
    metadata = getattr(response, "usage_metadata", None)
    if not isinstance(metadata, dict):
        return TokenUsage(0, 0)
    return TokenUsage(
        input_tokens=int(metadata.get("input_tokens") or 0),
        output_tokens=int(metadata.get("output_tokens") or 0),
    )


def load_llm_prices() -> Dict[str, Any]:
    """The pinned price table for the planner and the selected explainer,
    plus the project's own spend ceiling -- one reader for the repeats
    script, the route and the console, so no surface prices a token
    differently from another."""
    models = yaml.safe_load(_MODELS_PATH.read_text(encoding="utf-8"))
    planner = models["planner"]
    selected = models["explainer"]["selected"]
    explainer_price = next(
        c["price_usd_per_million"]
        for c in models["explainer"]["candidates"]
        if c["model"] == selected
    )
    return {
        "planner": {"model": planner["model"], **planner["price_usd_per_million"]},
        "explainer": {"model": selected, **explainer_price},
        "ceiling_usd": models["budget_ceiling_usd"],
    }


def _unwrap(role: str, result: Any) -> Any:
    """`with_structured_output(..., include_raw=True)` returns
    `{raw, parsed, parsing_error}`; the offline fakes return the parsed
    model directly. Both are accepted. A parsing error is raised as it
    would have been without `include_raw`; usage is recorded only when a
    session bound a log."""
    if not (isinstance(result, dict) and "parsed" in result):
        return result
    if result.get("parsing_error") is not None:
        raise result["parsing_error"]
    log = current_usage_log.get()
    if log is not None:
        log.append((role, usage_from_response(result.get("raw"))))
    return result["parsed"]


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# the single source for which prompt file version is live.
# Previously duplicated as a bare string literal in three places
# (`build.py`'s and `production.py`'s version tuples, and the
# `load_prompt_content(...)` call below) that could drift from each other
# with nothing to notice -- `test_declared_stage_artifacts.py`-style test
# now asserts `build.py`'s and `production.py`'s tuples agree, and both
# import the constant instead of retyping it.
PLANNER_PROMPT_VERSION = "planner_v2"
EXPLAINER_PROMPT_VERSION = "explainer_v1"


class StructuredLLM(Protocol):
    """Duck-typed: anything with `.invoke(messages) -> T` — a real
    `ChatOpenAI(...).with_structured_output(T)` Runnable, or a fake for
    tests."""

    def invoke(self, messages: List[BaseMessage]) -> Any: ...  # noqa: E704


def load_prompt_content(name: str) -> str:
    """Extracts the fenced instruction block under a prompt file's own
    "## Content" heading — everything else in the `.md` (prompting-
    technique rationale, unit-economics notes, worked-examples headers) is
    documentation for a human reader, never sent to the model. Raises
    naming the file rather than silently sending an empty or wrong prompt.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no prompt file named {name}.md in {_PROMPTS_DIR}")
    text = path.read_text(encoding="utf-8")

    marker = "## Content"
    if marker not in text:
        raise ValueError(f"{name}.md has no '## Content' section")
    after_marker = text[text.index(marker) + len(marker) :]

    if "```" not in after_marker:
        raise ValueError(f"{name}.md's '## Content' section has no fenced block")
    fence_start = after_marker.index("```")
    opening_line_end = after_marker.index("\n", fence_start)
    fence_close = after_marker.index("```", opening_line_end)
    return after_marker[opening_line_end + 1 : fence_close].strip()


def _dump(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        return cast(str, value.model_dump_json())
    if isinstance(value, list) and value and hasattr(value[0], "model_dump"):
        return json.dumps(
            [item.model_dump(mode="json") for item in value],
            default=str,
            ensure_ascii=False,
        )
    return json.dumps(value, default=str, ensure_ascii=False)


def render_planner_prompt(
    state: RecoveryState, tool_view: List[PlannerVisibleTool]
) -> str:
    template = load_prompt_content(PLANNER_PROMPT_VERSION)
    return template.format(
        diagnosis_json=_dump(state["diagnosis"]),
        disclosure_json=_dump(state["disclosure"]),
        channel_comparison_json=_dump(state["channel_comparison"]),
        planner_tool_view_json=json.dumps(
            [v.__dict__ for v in tool_view], default=str, ensure_ascii=False
        ),
    )


def render_explainer_prompt(proposal: ActionProposal) -> str:
    """The product name reaches this prompt only inside a `<product_data>`
    block (`tool_view.quote_product_text_as_data`) — never as bare text an
    injected instruction could blend into."""
    template = load_prompt_content(EXPLAINER_PROMPT_VERSION)
    summary = {
        "product_name": quote_product_text_as_data(proposal.product_name),
        "quantity": str(proposal.quantity),
        "expected_delta": str(proposal.expected_delta),
    }
    return template.format(action_proposal_json=json.dumps(summary, ensure_ascii=False))


def render_eval_judge_prompt(ua_eval_prompt: str, candidate_response: str) -> str:
    """UA-Eval's judge call (prompts/eval_judge_v1.md) — scores one
    candidate's response against the fixed rubric. Used only by
    `scripts/ua_eval_run.py`, never by the production graph."""
    template = load_prompt_content("eval_judge_v1")
    return template.format(
        ua_eval_prompt=ua_eval_prompt, candidate_response=candidate_response
    )


def build_eval_judge_llm(model: str, api_key: str) -> Any:
    """Constructs the real, live-network `ChatOpenAI` bound to OpenRouter
    with `EvalJudgeScore` structured output. UA-Eval territory — never
    called offline, never by the production graph."""
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    llm = ChatOpenAI(
        model=model, base_url=OPENROUTER_BASE_URL, api_key=SecretStr(api_key)
    )
    return llm.with_structured_output(EvalJudgeScore)


def build_candidate_llm(model: str, api_key: str) -> Any:
    """Constructs a plain (unstructured-output) `ChatOpenAI` bound to
    OpenRouter — UA-Eval candidates answer in free-form Ukrainian prose,
    not a fixed schema; the judge (above) is what scores that prose."""
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    return ChatOpenAI(
        model=model, base_url=OPENROUTER_BASE_URL, api_key=SecretStr(api_key)
    )


def make_planner_call(
    llm: StructuredLLM, tools_raw: Sequence[Mapping[str, Any]]
) -> Callable[[RecoveryState], SearchIntent]:
    system_text = load_prompt_content("recovery_system")

    def planner_call(state: RecoveryState) -> SearchIntent:
        tool_view = build_planner_tool_view(list(tools_raw))
        prompt = render_planner_prompt(state, tool_view)
        messages: List[BaseMessage] = [
            SystemMessage(content=system_text),
            HumanMessage(content=prompt),
        ]
        return cast(SearchIntent, _unwrap("planner", llm.invoke(messages)))

    return planner_call


def make_explainer_call(
    llm: StructuredLLM,
) -> Callable[[ActionProposal], ExplainerOutput]:
    system_text = load_prompt_content("recovery_system")

    def explainer_call(proposal: ActionProposal) -> ExplainerOutput:
        prompt = render_explainer_prompt(proposal)
        messages: List[BaseMessage] = [
            SystemMessage(content=system_text),
            HumanMessage(content=prompt),
        ]
        return cast(ExplainerOutput, _unwrap("explainer", llm.invoke(messages)))

    return explainer_call


def build_planner_llm(model: str, api_key: str, fallback: Optional[str] = None) -> Any:
    """Constructs the real, live-network `ChatOpenAI` bound to OpenRouter
    with `SearchIntent` structured output (see module docstring) — never
    called offline. `fallback` is accepted but not yet wired to an
    automatic retry: a fallback model must pass the same contract/golden
    gate as the primary before it can be trusted, and this change does not
    build that gate, so an unverified fallback stays unused rather than
    silently auto-switching.
    """
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    llm = ChatOpenAI(
        model=model, base_url=OPENROUTER_BASE_URL, api_key=SecretStr(api_key)
    )
    # `include_raw` so the provider's usage block reaches
    # `_unwrap`; the parsed model is what the node still receives.
    return llm.with_structured_output(SearchIntent, include_raw=True)


def build_explainer_llm(model: str, api_key: str) -> Any:
    """Constructs the real, live-network `ChatOpenAI` bound to OpenRouter
    with `ExplainerOutput` structured output. Never called offline."""
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    llm = ChatOpenAI(
        model=model, base_url=OPENROUTER_BASE_URL, api_key=SecretStr(api_key)
    )
    return llm.with_structured_output(ExplainerOutput, include_raw=True)
