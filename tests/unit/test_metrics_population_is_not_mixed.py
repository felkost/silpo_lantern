"""G9 follow-up (D84): the metrics population must not silently merge the
offline and live runs.

D80 fixed the metrics' population as the OFFLINE repeats, on the grounds
that a live LLM run is not reproducible by anyone cloning this repository.
It did not stop the live run's own records landing in the same directory
under the same filename pattern -- and `_load_run_records` globs the
pattern. Running both, as the follow-up did, silently doubled every
denominator from 33 to 66 and mixed two populations into one number that
describes neither.

Nothing would have flagged it: the metrics would still be 1.00 and 0.00,
just over a population the report misdescribes. Every record therefore
declares which population it belongs to, and the loader takes one.
"""

import json
from pathlib import Path

from scripts.compute_metrics import _load_run_records


def _write(directory: Path, name: str, population: str, count: int) -> None:
    (directory / name).write_text(
        json.dumps(
            {
                "population": population,
                "records": [{"case_id": f"GD-{i:02d}"} for i in range(count)],
            }
        ),
        encoding="utf-8",
    )


def test_only_the_offline_population_is_loaded_by_default(tmp_path: Path) -> None:
    _write(tmp_path, "g9_run_records_a.json", "offline", 3)
    _write(tmp_path, "g9_run_records_b.json", "live", 5)

    records = _load_run_records(tmp_path)

    assert (
        len(records) == 3
    ), "the live run's records were merged into the offline population"


def test_the_live_population_can_be_asked_for_explicitly(tmp_path: Path) -> None:
    _write(tmp_path, "g9_run_records_a.json", "offline", 3)
    _write(tmp_path, "g9_run_records_b.json", "live", 5)

    assert len(_load_run_records(tmp_path, population="live")) == 5


def test_a_record_file_with_no_population_is_refused_not_guessed(
    tmp_path: Path,
) -> None:
    """An older file predating this field must not be silently folded into
    whichever population happens to be asked for."""
    (tmp_path / "g9_run_records_old.json").write_text(
        json.dumps({"records": [{"case_id": "GD-01"}]}), encoding="utf-8"
    )

    try:
        _load_run_records(tmp_path)
    except ValueError as exc:
        assert "population" in str(exc)
    else:
        raise AssertionError("a file with no declared population was accepted")


def test_a_missing_directory_is_an_empty_population(tmp_path: Path) -> None:
    assert _load_run_records(tmp_path / "nope") == []
