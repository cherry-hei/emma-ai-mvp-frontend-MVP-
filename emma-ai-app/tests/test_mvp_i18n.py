"""zh-HK translation coverage (QA i18n task).

Background, because the reported bug was not the real one. The strings Cherry
flagged - 名冊, 督學, 艾瑪·艾, 贊同, 遵守, 氫氯噻嗪, 硬體 - have never existed in
any commit in this repository. They are Google Translate output: 氫氯噻嗪 is
hydrochlorothiazide for "HCA", 硬體 is computer hardware for "HW". What she was
looking at was Chrome auto-translating a page that was still mostly English,
because the dictionary only covered navigation.

These tests defend the actual fix:
  1. every key exists in both languages (a missing zh key silently renders the
     English string, which is what invites the browser to translate);
  2. no zh value is left as English;
  3. "Emma AI" is never transliterated;
  4. the specific mistranslations can never appear in our source.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LANG_TS = ROOT / "src" / "components" / "layout" / "LanguageContext.tsx"
VOCAB_TS = ROOT / "src" / "lib" / "vocab.ts"

requires_frontend = pytest.mark.skipif(
    not LANG_TS.exists(), reason="frontend not present (backend deployed without src/)"
)

# Strings that must never appear in our source: each is a machine translation of a
# term the homes have their own word for.
FORBIDDEN = {
    "名冊": "roster - the homes say 更表",
    "督學": "superintendent - a school inspector; the homes say 院長",
    "艾瑪": "Emma AI is a product name and is not transliterated",
    "氫氯噻嗪": "hydrochlorothiazide - machine translation of the rank code HCA",
    "硬體": "computer hardware - machine translation of the rank code HW",
    "贊同": "approval - the homes say 審批",
    "遵守": "compliance - the homes say 合規",
}


def _dict_block(text: str, name: str) -> dict[str, str]:
    m = re.search(
        rf"const {name}: Record<string, string> = \{{(.*?)\n\}}", text, re.DOTALL
    )
    assert m, f"could not find the {name} dictionary"
    return dict(re.findall(r"^\s*(\w+)\s*:\s*'((?:[^'\\]|\\.)*)'", m.group(1), re.MULTILINE))


@requires_frontend
def test_zh_and_en_cover_the_same_keys():
    text = LANG_TS.read_text(encoding="utf-8")
    en, zh = _dict_block(text, "EN"), _dict_block(text, "ZH")
    assert en, "EN dictionary parsed empty"
    missing_zh = sorted(set(en) - set(zh))
    missing_en = sorted(set(zh) - set(en))
    assert not missing_zh, f"keys with no Chinese translation: {missing_zh}"
    assert not missing_en, f"zh keys with no English original: {missing_en}"


@requires_frontend
def test_no_zh_value_is_still_english():
    """A zh entry with no CJK character is an untranslated placeholder. Latin is
    allowed alongside CJK (unit codes, 'AI', 'P更'), just not on its own."""
    zh = _dict_block(LANG_TS.read_text(encoding="utf-8"), "ZH")
    untranslated = sorted(
        k for k, v in zh.items()
        if not re.search(r"[一-鿿]", v) and re.search(r"[A-Za-z]{3}", v)
    )
    assert not untranslated, f"zh values that are still English: {untranslated}"


def _strip_comments(src: str) -> str:
    """Drop // and /* */ so the scan sees only what can reach a screen.

    Deliberately crude - it will also blank a `//` inside a string literal. That
    costs nothing here (we are looking for CJK terms, not URLs) and it means a
    comment may name a mistranslation in order to explain it, which is how the
    reason this test exists stays written down next to the code."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


@requires_frontend
@pytest.mark.parametrize("bad", sorted(FORBIDDEN))
def test_machine_translations_are_absent_from_the_frontend(bad):
    hits = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src").rglob("*.ts*")
        if bad in _strip_comments(p.read_text(encoding="utf-8"))
    ]
    assert not hits, f"{bad!r} ({FORBIDDEN[bad]}) found in {hits}"


@requires_frontend
def test_emma_ai_is_never_translated():
    zh = _dict_block(LANG_TS.read_text(encoding="utf-8"), "ZH")
    for key, value in zh.items():
        if "emma" in value.lower():
            assert "Emma AI" in value, f"{key} mangles the product name: {value!r}"


@requires_frontend
@pytest.mark.parametrize("code", ["A", "B", "E", "P", "N", "AN"])
def test_letter_shift_codes_keep_the_letter_in_both_languages(code):
    """A/P/N are letters, not times of day (Cherry, 1 Aug 2026).

    Both NGOs print the same letters and hang different hours off them - NAAC's A
    shift is 07:15-15:15 and its A230 runs 14:30-22:30. So "Morning" and 早更 are
    not a translation choice, they are a factual error, and the fix has to hold on
    both sides of the dictionary. The hours live in `shift_definitions`.
    """
    entry = re.search(
        rf"^\s*{code}:\s*\{{\s*en:\s*'([^']*)',\s*zh:\s*'([^']*)'",
        VOCAB_TS.read_text(encoding="utf-8"), re.MULTILINE)
    assert entry, f"shift code {code} is missing from SHIFTS in vocab.ts"
    en, zh = entry.group(1), entry.group(2)
    assert zh == f"{code}更", f"{code} zh label should be '{code}更', got {zh!r}"
    assert en == f"{code} shift", f"{code} en label should be '{code} shift', got {en!r}"


@requires_frontend
@pytest.mark.parametrize("banned", ["早更", "午更", "夜更", "黃昏更"])
def test_time_of_day_shift_names_are_gone(banned):
    """These read as correct Chinese, which is what makes them dangerous - nothing
    would flag them on review, and a P更 labelled 午更 tells a reader 14:30-22:30
    is the afternoon."""
    hits = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src").rglob("*.ts*")
        if banned in _strip_comments(p.read_text(encoding="utf-8"))
    ]
    assert not hits, f"{banned!r} is a time-of-day shift name; use the letter. Found in {hits}"


@requires_frontend
def test_every_rank_code_has_a_chinese_label():
    """A bare Latin rank code in zh mode is what the browser mistranslated, so
    every rank the backend can emit needs an entry in vocab.ts."""
    from emma_core.constants import Rank

    labelled = set(re.findall(r"^\s*(\w+):\s*\{ en:", VOCAB_TS.read_text(encoding="utf-8"),
                              re.MULTILINE))
    missing = sorted({r.value for r in Rank} - labelled)
    assert not missing, f"rank codes with no zh label: {missing}"
