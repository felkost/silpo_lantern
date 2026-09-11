"""The documentation site exists in English and Ukrainian, and the two
must stay the same document in two languages — not one that quietly grew
a section the other never got.

Checked here rather than by eye: the same pages, the same section
anchors in the same order, the same diagram slots, and no English left
inside the Ukrainian headings (the failure mode of a half-finished
translation).
"""

import re

import pytest

from scripts import report_content_en as EN
from scripts import report_content_uk as UK
from src.lantern.config import PROJECT_ROOT

REPORTS = PROJECT_ROOT / "docs" / "reports"


def test_both_languages_declare_the_same_pages() -> None:
    assert set(EN.BODIES) == set(UK.BODIES)
    assert [f for f, _, _ in EN.NAV] == [f for f, _, _ in UK.NAV]
    assert set(EN.TITLES) == set(UK.TITLES) == set(EN.BODIES)


@pytest.mark.parametrize("page", sorted(EN.BODIES))
def test_the_same_sections_in_the_same_order(page: str) -> None:
    """A section anchor is what the 'on this page' list and every
    cross-page link point at, so a missing one is a broken link in one
    language only."""
    en_ids = re.findall(r'<h2 id="([^"]+)"', EN.BODIES[page])
    uk_ids = re.findall(r'<h2 id="([^"]+)"', UK.BODIES[page])
    assert en_ids == uk_ids, page
    assert [a for a, _ in EN.SECTIONS[page]] == [a for a, _ in UK.SECTIONS[page]]
    assert [a for a, _ in EN.SECTIONS[page]] == en_ids, f"{page}: on-page list drifted"


@pytest.mark.parametrize("page", sorted(EN.BODIES))
def test_the_same_diagrams_in_the_same_order(page: str) -> None:
    """Both versions must show the same evidence: a diagram dropped from
    one language is a different argument, not a translation."""
    en_slots = re.findall(r"\{\{ (\w+_svg) \}\}", EN.BODIES[page])
    uk_slots = re.findall(r"\{\{ (\w+_svg) \}\}", UK.BODIES[page])
    assert en_slots == uk_slots, page


@pytest.mark.parametrize("page", sorted(EN.BODIES))
def test_the_ukrainian_headings_are_ukrainian(page: str) -> None:
    """The half-translated page is the likely failure, and it shows up in
    the headings first. Identifiers from the code (`order.cost.min`,
    `args_hash`) stay as they are and live in <code>, which is excluded."""
    body = re.sub(r"<code>.*?</code>", "", UK.BODIES[page], flags=re.S)
    headings = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S)
    headings += [name for _, name in UK.SECTIONS[page]]
    headings += [UK.TITLES[page][1]]
    for heading in headings:
        text = re.sub(r"<[^>]+>", "", heading)
        assert re.search(r"[а-яіїєґА-ЯІЇЄҐ]", text), f"{page}: untranslated {text!r}"


def test_every_rendered_page_exists_in_both_languages() -> None:
    for page in EN.BODIES:
        assert (REPORTS / page).exists(), f"{page} not rendered (run make report)"
        assert (REPORTS / "uk" / page).exists(), f"uk/{page} not rendered"


def test_the_language_switch_points_at_the_same_page() -> None:
    """Switching language must land on the same subject, not on the other
    language's home page."""
    for page in EN.BODIES:
        en = (REPORTS / page).read_text(encoding="utf-8")
        uk = (REPORTS / "uk" / page).read_text(encoding="utf-8")
        assert f'<a href="uk/{page}"' in en, page
        assert f'<a href="../{page}"' in uk, page
