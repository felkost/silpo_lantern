"""G5+G6 (D-G5-05): (re)generates `reviewed_tools.json`'s `tool_hashes`
object from the tracked contract fixture -- never hand-typed, since a
hand-typed hash is unverifiable against anything.

Usage:
    .venv/Scripts/python.exe scripts/generate_reviewed_tool_hashes.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT  # noqa: E402
from src.lantern.mcp.client import compute_per_tool_schema_hashes  # noqa: E402

FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
)
REVIEWED_TOOLS_PATH = PROJECT_ROOT / "src" / "lantern" / "mcp" / "reviewed_tools.json"


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    tools_raw = fixture["payload"]["tools"]
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
