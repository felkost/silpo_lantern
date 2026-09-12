"""(re)generates `reviewed_tools.json`'s `tool_hashes`
object from the tracked contract fixture -- never hand-typed, since a
hand-typed hash is unverifiable against anything.

used to hardcode
`tools_list_2026-09-05.json`. Running it today would have silently
REVERTED the reviewed baseline to the stale hashes and broken every live
write with a schema-drift refusal -- five tools drifted since.
Fixed to read the fixture named in `reviewed_tools.json`'s own `source`
field, and to refuse (non-zero exit) when that fixture's own stated
`source_schema_hash` disagrees with a freshly recomputed one -- a
tampered or stale-but-unnoticed fixture must not be trusted silently.

Usage:
    .venv/Scripts/python.exe scripts/generate_reviewed_tool_hashes.py
"""

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT  # noqa: E402
from src.lantern.mcp.client import (  # noqa: E402
    compute_per_tool_schema_hashes,
    compute_schema_hash,
)

REVIEWED_TOOLS_PATH = PROJECT_ROOT / "src" / "lantern" / "mcp" / "reviewed_tools.json"


def fixture_path() -> Path:
    """The fixture `reviewed_tools.json` itself claims as its baseline --
    never hardcoded, so this script and the baseline it edits can never
    silently disagree about which snapshot is current."""
    reviewed = json.loads(REVIEWED_TOOLS_PATH.read_text(encoding="utf-8"))
    return PROJECT_ROOT / str(reviewed["source"])


def main(fixture_path_override: Optional[Path] = None) -> None:
    path = fixture_path_override or fixture_path()
    fixture = json.loads(path.read_text(encoding="utf-8"))
    tools_raw = fixture["payload"]["tools"]

    recomputed_whole_hash = compute_schema_hash(tools_raw)
    stated_whole_hash = fixture.get("source_schema_hash")
    if stated_whole_hash != recomputed_whole_hash:
        raise SystemExit(
            f"refusing to regenerate: {path} claims source_schema_hash "
            f"{stated_whole_hash!r}, but the tools it actually carries "
            f"hash to {recomputed_whole_hash!r} -- fixture is tampered "
            "or stale"
        )

    hashes = compute_per_tool_schema_hashes(tools_raw)

    reviewed = json.loads(REVIEWED_TOOLS_PATH.read_text(encoding="utf-8"))
    reviewed_hashes = {
        name: h for name, h in hashes.items() if name in reviewed["names"]
    }
    reviewed["tool_hashes"] = reviewed_hashes
    REVIEWED_TOOLS_PATH.write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(reviewed_hashes)} per-tool hashes to {REVIEWED_TOOLS_PATH}")


if __name__ == "__main__":
    main()
