"""regenerates `reviewed_tools.json`'s per-tool hashes from a
LIVE `tools/list` capture, through the exact code path production uses
(`mcp.session.list_tools_raw`), so the reviewed baseline stops being
computed against the historical raw-capture fixture (a different
canonicalisation, per the own measured finding) and starts matching
what the live schema-drift check will actually compare against.

Read-only, no LLM spend, no cart mutation. Author-run: needs the cached
OAuth token at `.cache/silpo_mcp_token.json`.

Usage:
    .venv/Scripts/python.exe scripts/g5_regenerate_live_tool_hashes.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT  # noqa: E402
from src.lantern.mcp.client import compute_per_tool_schema_hashes  # noqa: E402
from src.lantern.mcp.session import list_tools_raw  # noqa: E402

REVIEWED_TOOLS_PATH = PROJECT_ROOT / "src" / "lantern" / "mcp" / "reviewed_tools.json"


def main() -> None:
    print("Fetching live tools/list...")
    tools_raw = list_tools_raw()
    print(f"Got {len(tools_raw)} tools live.")

    hashes = compute_per_tool_schema_hashes(tools_raw)
    reviewed = json.loads(REVIEWED_TOOLS_PATH.read_text(encoding="utf-8"))

    reviewed_names = set(reviewed["names"])
    live_names = set(hashes)
    missing_from_live = reviewed_names - live_names
    new_since_review = live_names - reviewed_names
    if missing_from_live:
        print(
            f"WARNING: {len(missing_from_live)} reviewed tool(s) no longer "
            f"appear live: {sorted(missing_from_live)}"
        )
    if new_since_review:
        print(
            f"NOTE: {len(new_since_review)} tool(s) exist live but are not "
            f"yet reviewed (they stay quarantined): {sorted(new_since_review)}"
        )

    reviewed_hashes = {name: h for name, h in hashes.items() if name in reviewed_names}
    reviewed["tool_hashes"] = reviewed_hashes
    reviewed["tool_hashes_source"] = (
        "live (list_tools_raw, model_dump canonicalisation)"
    )
    REVIEWED_TOOLS_PATH.write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(reviewed_hashes)} live per-tool hashes to {REVIEWED_TOOLS_PATH}")


if __name__ == "__main__":
    main()
