"""F7: CLI wrapper around
`src.lantern.mcp.sanitizer.sanitize_payload` — reads a raw captured MCP
payload (from `scripts/capture_fixture.py`, never committed), wraps the
sanitized result in the fixture envelope schema, and refuses to write if the
output still matches any of `scripts/secret_scan.py`'s own patterns (same
threat, same rules — reused, not duplicated).

This is the last of two required steps before a fixture reaches
`datasets/fixtures/sanitized/`: sanitize_payload's allow-list is a first cut
(F7) and every output here still needs a **human review pass** before
commit — this script does not replace that review, it is the mechanical
half of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.secret_scan import PATTERNS  # noqa: E402
from src.lantern.mcp.sanitizer import sanitize_payload  # noqa: E402


def build_envelope(
    fixture_id: str,
    source_schema_hash: str,
    payload: Dict[str, Any],
    origin: str = "recorded",
    generator_version: str = "n/a-recorded",
    seed: Optional[int] = None,
    transformations: Optional[List[str]] = None,
    expected_outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "origin": origin,
        "source_schema_hash": source_schema_hash,
        "generator_version": generator_version,
        "seed": seed,
        "transformations": transformations or [],
        "expected_outcome": expected_outcome or {},
        "payload": payload,
    }


def find_secret_shaped_matches(envelope: Dict[str, Any]) -> List[str]:
    text = json.dumps(envelope, ensure_ascii=False)
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sanitize a raw captured MCP fixture (F7) into "
            "datasets/fixtures/sanitized/."
        )
    )
    parser.add_argument(
        "raw_path", type=Path, help="Raw payload, from capture_fixture.py"
    )
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--source-schema-hash", required=True)
    parser.add_argument(
        "--out-dir", type=Path, default=Path("datasets/fixtures/sanitized")
    )
    args = parser.parse_args(argv)

    raw = json.loads(args.raw_path.read_text(encoding="utf-8"))
    envelope = build_envelope(
        fixture_id=args.fixture_id,
        source_schema_hash=args.source_schema_hash,
        payload=sanitize_payload(raw),
    )

    findings = find_secret_shaped_matches(envelope)
    if findings:
        print(f"REFUSED: sanitized output still matches {findings}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.fixture_id}.json"
    out_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_path} — still needs human review before commit (F7)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
