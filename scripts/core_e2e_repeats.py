"""G9 (G9.6): the 18 core E2E repeats -- GD-01..06 x 3, with a LIVE
planner and explainer against REPLAYED MCP and Postgres.

The configuration the author approved at the G8+G9 kickoff: only the two
LLM boundaries are live. MCP stays on the tape, so the repeats measure
planner/explainer non-determinism without touching a real cart and
without a real write. `replay()`'s optional `planner_call`/
`explainer_call` (D62/D-G9-05) are what make that possible, and
`mcp_by_tool`'s fallback queue is what survives the live planner's own
varying search terms -- an args-keyed tape could never match them.

Accounting is NOT done here: `domain/repeat_accounting.py` owns the rules
(denominator always 18, `blocked` counts against the ratio, more than
three blocked invalidates the run, a safety failure blocks regardless of
the average) so they are unit-testable without a live call.

Tokens and cost come from the provider's OWN reported usage, never an
estimate -- D59 leaves no other source, and an invented token count would
land in a report judged against a $20 project ceiling. `include_raw=True`
is what keeps the raw response (and its `usage_metadata`) reachable
alongside the parsed structured output; that is why this script builds
its own live callables instead of reusing `llm_adapter`'s, which
deliberately return only the parsed object.

LIVE LLM SPEND. Never run by the gate. Needs the author's explicit
go-ahead, with the cost estimate shown first (`--estimate-only`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from src.lantern.config import PROJECT_ROOT, load_env  # noqa: E402
from src.lantern.domain.repeat_accounting import (  # noqa: E402
    RepeatOutcome,
    RepeatRunInvalid,
    TokenUsage,
    cost_usd,
    summarise_repeats,
    total_cost_usd,
)
from src.lantern.observability.tracer import (  # noqa: E402
    install_trace_redaction,
)
from src.lantern.graph.replay import (  # noqa: E402
    ReplayMismatch,
    load_bundle,
    replay,
)

CASES_DIR = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "cases"
MANIFEST_PATH = PROJECT_ROOT / "datasets" / "fixtures" / "manifest.json"
MODELS_PATH = PROJECT_ROOT / "config" / "models.yaml"
EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"

CORE_CASE_IDS = ["GD-01", "GD-02", "GD-03", "GD-04", "GD-05", "GD-06"]
REPEATS_PER_CASE = 3


def usage_from_response(response: Any) -> TokenUsage:
    """Reads the provider's own usage block off a raw LangChain message.

    A response carrying none records ZEROS, never an estimate: an
    unmeasured call must stay visibly unmeasured rather than contribute a
    guessed number to a cost report."""
    metadata = getattr(response, "usage_metadata", None)
    if not isinstance(metadata, dict):
        return TokenUsage(0, 0)
    return TokenUsage(
        input_tokens=int(metadata.get("input_tokens") or 0),
        output_tokens=int(metadata.get("output_tokens") or 0),
    )


def _prices() -> Dict[str, Dict[str, float]]:
    models = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
    planner = models["planner"]
    explainer_selected = models["explainer"]["selected"]
    explainer_price = next(
        c["price_usd_per_million"]
        for c in models["explainer"]["candidates"]
        if c["model"] == explainer_selected
    )
    return {
        "planner": {
            "model": planner["model"],
            **planner["price_usd_per_million"],
        },
        "explainer": {"model": explainer_selected, **explainer_price},
    }


def _bundle_path_for(case: Dict[str, Any]) -> Optional[Path]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixture_id = case["input"]["fixture_id"]
    for entry in manifest["fixtures"]:
        if entry["fixture_id"] == fixture_id:
            return PROJECT_ROOT / entry["path"]
    return None


def _load_core_cases() -> List[Dict[str, Any]]:
    cases = []
    for case_id in CORE_CASE_IDS:
        path = CASES_DIR / f"{case_id}.json"
        if not path.is_file():
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        if case.get("mode") != "replay":
            continue
        cases.append(case)
    return cases


TRACE_TAGS = ["g9", "core-e2e-repeats"]


def _live_callables(usage_log: List[Tuple[str, TokenUsage]]):
    """Builds the REAL planner/explainer, each wrapped so the raw
    response's usage is recorded alongside the parsed output."""
    import os

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    from src.lantern.graph.build import policy_registry_version
    from src.lantern.graph.llm_adapter import (
        OPENROUTER_BASE_URL,
        load_prompt_content,
        render_explainer_prompt,
        render_planner_prompt,
    )
    from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
    from src.lantern.graph.llm_adapter import (
        EXPLAINER_PROMPT_VERSION,
        PLANNER_PROMPT_VERSION,
    )
    from src.lantern.graph.tool_view import build_planner_tool_view
    from src.lantern.mcp.client import compute_schema_hash
    from src.lantern.mcp.session import list_tools_raw
    from src.lantern.observability.tracer import (
        redact_explainer_input,
        redact_planner_input,
        traced_llm_call,
    )

    api_key = os.environ["OPENROUTER_API_KEY"]
    prices = _prices()
    system_text = load_prompt_content("recovery_system")
    tools_raw = list_tools_raw()

    planner_llm = ChatOpenAI(
        model=prices["planner"]["model"],
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(api_key),
    ).with_structured_output(SearchIntent, include_raw=True)
    explainer_llm = ChatOpenAI(
        model=prices["explainer"]["model"],
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(api_key),
    ).with_structured_output(ExplainerOutput, include_raw=True)

    def planner_call(state: Any) -> SearchIntent:
        prompt = render_planner_prompt(state, build_planner_tool_view(list(tools_raw)))
        result = planner_llm.invoke(
            [SystemMessage(content=system_text), HumanMessage(content=prompt)]
        )
        usage_log.append(("planner", usage_from_response(result.get("raw"))))
        return result["parsed"]

    def explainer_call(proposal: Any) -> ExplainerOutput:
        prompt = render_explainer_prompt(proposal)
        result = explainer_llm.invoke(
            [SystemMessage(content=system_text), HumanMessage(content=prompt)]
        )
        usage_log.append(("explainer", usage_from_response(result.get("raw"))))
        parsed = result["parsed"]
        return ExplainerOutput(
            **{**parsed.model_dump(), "action_id": proposal.action_id}
        )

    # G9 (D78): the same wrapper `build_recovery_graph` puts on these two
    # calls. Without it the run's 63 LLM calls reached LangSmith as bare
    # LangGraph auto-instrumentation -- no named span, and metadata
    # carrying nothing but `ls_integration` and a revision id, so no
    # trace could say which prompt version or model produced it.
    version_tuple = {
        "schema_hash": compute_schema_hash(list(tools_raw)),
        "policy_registry_version": policy_registry_version(),
        "planner_model_id": prices["planner"]["model"],
        "planner_prompt_version": PLANNER_PROMPT_VERSION,
        "explainer_model_id": prices["explainer"]["model"],
        "explainer_prompt_version": EXPLAINER_PROMPT_VERSION,
    }
    tags = TRACE_TAGS
    return (
        traced_llm_call(
            "planner", planner_call, redact_planner_input, version_tuple, tags
        ),
        traced_llm_call(
            "explainer", explainer_call, redact_explainer_input, version_tuple, tags
        ),
    )


def build_run_record(
    *, case_id: str, repeat: int, thread_id: str, status: str, result: Any
) -> Dict[str, Any]:
    """One run's evidence, in the shape `compute_metrics._load_run_records`
    reads (D80).

    Everything here is READ OFF the run, never asserted about it: the
    journal claims are the rows the graph actually wrote before each write
    call, `written_args_hash` is recomputed from the args the player was
    actually asked to send, and `actually_cleared` is re-derived from the
    receipt's own `after_state` validations rather than copied from the
    receipt's `blocker_cleared` claim -- otherwise FalseRecovery compares
    a number with itself and can never be anything but zero.
    """
    from src.lantern.domain.consent_hash import compute_args_hash

    player = result.player
    receipts = list(result.receipts)

    # The one write shape: the wire payload carries both a cart id and a
    # products list. Matched by SHAPE, not by importing the write
    # allowlist -- that constant may not leave `lantern/safety/**`.
    write_args_by_order = [
        args
        for _tool, args in (player.calls if player else [])
        if "shoppingCartId" in args and "products" in args
    ]

    consents = dict(player.consents) if player else {}
    claims = [
        {
            "owner": owner,
            "cart_id": cart_id,
            "action_id": action_id,
            "state": state,
        }
        for (owner, cart_id, action_id), state in (
            (player.journal if player else {})
        ).items()
    ]

    receipt_rows = []
    for index, receipt in enumerate(receipts):
        after = receipt.after_state or {}
        validations = after.get("validations") or []
        consent = consents.get(receipt.action_id)
        written = (
            write_args_by_order[index] if index < len(write_args_by_order) else None
        )
        receipt_rows.append(
            {
                "action_id": receipt.action_id,
                "kind": getattr(receipt, "kind", "add"),
                "expected_delta": (
                    str(receipt.expected_delta)
                    if receipt.expected_delta is not None
                    else None
                ),
                "actual_delta": (
                    str(receipt.actual_delta)
                    if receipt.actual_delta is not None
                    else None
                ),
                "claimed_blocker_cleared": bool(receipt.blocker_cleared),
                "actually_cleared": not any(
                    v.get("level") == "error" for v in validations
                ),
                "consented_args_hash": consent.args_hash if consent else None,
                "written_args_hash": (
                    compute_args_hash(written) if written is not None else None
                ),
            }
        )

    return {
        "case_id": case_id,
        "repeat": repeat,
        "thread_id": thread_id,
        "status": status,
        "completed": status == "pass",
        "journal_claims": claims,
        "consent_action_ids": sorted(consents),
        "receipts": receipt_rows,
        # A replay cannot audit what the Silpo app renders, so visibility
        # is never verified here and the row is excluded from
        # DisclosureRate entirely -- "unknown" is not "hidden".
        "disclosure": {"had_invisible_constraint": None, "visibility_verified": False},
    }


def _classify(case: Dict[str, Any], result: Any) -> Tuple[str, str]:
    expected = case["expected_outcome"]
    actual_status = result.final_state.get("status")
    if "status" in expected and actual_status != expected["status"]:
        return "fail", (
            f"expected status {expected['status']!r}, got {actual_status!r}"
        )
    if (
        "receipts_count" in expected
        and len(result.receipts) != expected["receipts_count"]
    ):
        return "fail", (
            f"expected {expected['receipts_count']} receipt(s), "
            f"got {len(result.receipts)}"
        )
    return "pass", ""


def run_repeats(*, estimate_only: bool, offline: bool = False) -> Dict[str, Any]:
    cases = _load_core_cases()
    expected_total = len(CORE_CASE_IDS) * REPEATS_PER_CASE

    if estimate_only:
        prices = _prices()
        models = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
        planner_tokens = models["planner"]["expected_tokens"]
        explainer_tokens = models["explainer"]["expected_tokens"]
        per_run = cost_usd(
            TokenUsage(planner_tokens["input"], planner_tokens["output"]),
            input_usd_per_million=prices["planner"]["input"],
            output_usd_per_million=prices["planner"]["output"],
        ) + cost_usd(
            TokenUsage(explainer_tokens["input"], explainer_tokens["output"]),
            input_usd_per_million=prices["explainer"]["input"],
            output_usd_per_million=prices["explainer"]["output"],
        )
        return {
            "estimate_only": True,
            "cases_found": [c["case_id"] for c in cases],
            "planned_repeats": expected_total,
            "estimated_usd_per_run": round(per_run, 6),
            "estimated_usd_total": round(per_run * expected_total, 4),
            "note": (
                "Estimate from config/models.yaml's declared expected_tokens, "
                "NOT a measurement. The real figure is recomputed from the "
                "provider's own usage after the run."
            ),
        }

    # D80: `--offline` runs the same 18 repeats against each bundle's OWN
    # recorded planner and explainer. It is not a cheaper substitute for
    # the live configuration -- section 13.4's repeats measure live
    # planner non-determinism and only the live run can -- but it is the
    # population the METRICS are computed over, because D61 requires
    # numbers a fresh clone can reproduce, and nobody can reproduce
    # someone else's live LLM run.
    if offline:
        planner_call, explainer_call = None, None
        prices = _prices()
        usage_log: List[Tuple[str, TokenUsage]] = []
        return _execute(
            cases=cases,
            expected_total=expected_total,
            planner_call=planner_call,
            explainer_call=explainer_call,
            usage_log=usage_log,
            prices=prices,
        )

    load_env()
    # D-G7-15, and D78: before anything creates a LangSmith client or emits
    # a span. LangGraph instruments every node itself and serialises the
    # whole RecoveryState, so without this the cart's coordinates ride
    # along in a neighbouring span -- measured on a live run 2026-09-07,
    # and this runner was making live calls without it.
    install_trace_redaction()
    usage_log = []
    planner_call, explainer_call = _live_callables(usage_log)
    prices = _prices()
    return _execute(
        cases=cases,
        expected_total=expected_total,
        planner_call=planner_call,
        explainer_call=explainer_call,
        usage_log=usage_log,
        prices=prices,
    )


def _execute(
    *,
    cases: List[Dict[str, Any]],
    expected_total: int,
    planner_call: Any,
    explainer_call: Any,
    usage_log: List[Tuple[str, TokenUsage]],
    prices: Dict[str, Any],
) -> Dict[str, Any]:
    runs: List[Dict[str, Any]] = []
    outcomes: List[RepeatOutcome] = []
    # D80: the per-run evidence `compute_metrics.py` reads. Separate from
    # the summary above, which is a report for a human -- these are rows.
    records: List[Dict[str, Any]] = []

    for case in cases:
        bundle_path = _bundle_path_for(case)
        for repeat_index in range(REPEATS_PER_CASE):
            started = time.monotonic()
            thread_id = f"g9-repeat-{case['case_id']}-{repeat_index + 1}"
            status, reason = "pass", ""
            result = None
            try:
                if bundle_path is None:
                    raise ReplayMismatch(
                        f"no bundle in the manifest for "
                        f"{case['input']['fixture_id']!r}"
                    )
                result = replay(
                    load_bundle(bundle_path),
                    planner_call=planner_call,
                    explainer_call=explainer_call,
                    thread_id=thread_id,
                    tags=TRACE_TAGS,
                )
                status, reason = _classify(case, result)
            except ReplayMismatch as exc:
                # D-G9-08: a tape miss and a live planner regression raise
                # identically, so this is `blocked` -- never `fail`, and
                # never excluded from the denominator either.
                status, reason = "blocked", f"ReplayMismatch: {exc}"
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                status, reason = "fail", f"{type(exc).__name__}: {exc}"

            runs.append(
                {
                    "case_id": case["case_id"],
                    "repeat": repeat_index + 1,
                    "fixture_id": case["input"]["fixture_id"],
                    "status": status,
                    "reason": reason,
                    "thread_id": thread_id,
                    "latency_seconds": round(time.monotonic() - started, 3),
                }
            )
            outcomes.append(
                RepeatOutcome(case_id=case["case_id"], status=status, reason=reason)
            )
            if result is not None:
                records.append(
                    build_run_record(
                        case_id=case["case_id"],
                        repeat=repeat_index + 1,
                        thread_id=thread_id,
                        status=status,
                        result=result,
                    )
                )

    costs = [
        cost_usd(
            usage,
            input_usd_per_million=prices[role]["input"],
            output_usd_per_million=prices[role]["output"],
        )
        for role, usage in usage_log
    ]
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_total": expected_total,
        "runs": runs,
        "records": records,
        "llm_calls": len(usage_log),
        "input_tokens": sum(u.input_tokens for _, u in usage_log),
        "output_tokens": sum(u.output_tokens for _, u in usage_log),
        "measured_cost_usd": total_cost_usd(costs),
        "models": {role: prices[role]["model"] for role in ("planner", "explainer")},
    }

    try:
        summary = summarise_repeats(outcomes, expected_total=expected_total)
        report["summary"] = {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "blocked": summary.blocked,
            "ratio": round(summary.ratio, 4),
            "meets_085": summary.meets_threshold(0.85),
        }
    except RepeatRunInvalid as exc:
        # Reported as an invalid run, never silently rescaled to a ratio.
        report["summary"] = {"invalid": True, "reason": str(exc)}

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "run the same repeats against each bundle's own recorded "
            "planner/explainer -- no live call, no cost; the population "
            "the metrics are computed over (D80)"
        ),
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="print the cost estimate and the cases found, make no live call",
    )
    args = parser.parse_args()

    report = run_repeats(estimate_only=args.estimate_only, offline=args.offline)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.estimate_only:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        records_out = EVIDENCE_DIR / f"g9_run_records_{stamp}.json"
        records_out.write_text(
            json.dumps({"records": report.pop("records", [])}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {records_out.relative_to(PROJECT_ROOT)}")
        out = EVIDENCE_DIR / f"g9_core_e2e_repeats_{stamp}.json"
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
