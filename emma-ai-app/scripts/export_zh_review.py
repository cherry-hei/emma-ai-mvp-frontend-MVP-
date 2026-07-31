"""Export every user-facing string as a bilingual review sheet.

Cherry offered to review the zh translation file. Pointing her at
`LanguageContext.tsx` and `vocab.ts` would mean reading TypeScript to find the
strings, so this flattens both into one table she can mark up and hand back.

    python scripts/export_zh_review.py            # -> docs/ZH_REVIEW.md
    python scripts/export_zh_review.py --csv      # -> docs/ZH_REVIEW.csv

Regenerate after touching either source file; the header carries the commit so a
returned review can be matched to what it was reviewing.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
LANG_TS = ROOT / "src" / "components" / "layout" / "LanguageContext.tsx"
VOCAB_TS = ROOT / "src" / "lib" / "vocab.ts"
OUT_DIR = ROOT / "docs"

# Section comments in the dictionaries ("// roster page") become table groupings.
SECTION_RE = re.compile(r"^\s*//\s*(.+?)\s*$")
# MULTILINE matters: `^` has to anchor per line, not once at the start of the
# block, or findall returns only the first entry.
ENTRY_RE = re.compile(r"^\s*(\w+)\s*:\s*'((?:[^'\\]|\\.)*)'", re.MULTILINE)
TERM_RE = re.compile(r"^\s*(\w+):\s*\{\s*en:\s*'([^']*)',\s*zh:\s*'([^']*)'")
TABLE_RE = re.compile(r"export const (\w+): Record<string, Term> = \{(.*?)\n\}", re.DOTALL)


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - a review sheet is still useful without it
        return "unknown"


def _dict_block(text: str, name: str) -> dict[str, str]:
    m = re.search(rf"const {name}: Record<string, string> = \{{(.*?)\n\}}", text, re.DOTALL)
    if not m:
        return {}
    return dict(ENTRY_RE.findall(m.group(1)))


def _ui_rows() -> list[tuple[str, str, str, str]]:
    text = LANG_TS.read_text(encoding="utf-8")
    en, zh = _dict_block(text, "EN"), _dict_block(text, "ZH")
    block = re.search(r"const ZH: Record<string, string> = \{(.*?)\n\}", text, re.DOTALL)
    section, rows = "navigation", []
    for line in (block.group(1).splitlines() if block else []):
        entry = ENTRY_RE.match(line)
        if entry:
            key = entry.group(1)
            rows.append((section, key, en.get(key, "(missing)"), zh.get(key, "(missing)")))
            continue
        head = SECTION_RE.match(line)
        if head and not head.group(1).startswith(("Hong Kong", '"Emma AI"', "艾瑪")):
            section = head.group(1)
    return rows


def _vocab_rows() -> list[tuple[str, str, str, str]]:
    text = VOCAB_TS.read_text(encoding="utf-8")
    rows = []
    for name, body in TABLE_RE.findall(text):
        for code, en, zh in TERM_RE.findall(body):
            rows.append((f"vocab: {name.lower()}", code, en, zh))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help="write CSV instead of Markdown")
    args = ap.parse_args()

    rows = _ui_rows() + _vocab_rows()
    OUT_DIR.mkdir(exist_ok=True)

    if args.csv:
        out = OUT_DIR / "ZH_REVIEW.csv"
        with out.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["section", "key", "english", "chinese_current", "chinese_suggested", "comment"])
            for section, key, en, zh in rows:
                w.writerow([section, key, en, zh, "", ""])
    else:
        out = OUT_DIR / "ZH_REVIEW.md"
        lines = [
            "# Emma AI - Chinese (zh-HK) review sheet",
            "",
            f"Generated from `src/components/layout/LanguageContext.tsx` and "
            f"`src/lib/vocab.ts` at commit `{_commit()}`. {len(rows)} strings.",
            "",
            "**How to review:** add a column or annotate any row whose Chinese is wrong.",
            "Terminology follows the homes' own duty rosters, so where our wording differs",
            "from what staff actually say on the floor, the floor wins.",
            "",
            "Two notes on things that are intentional:",
            "",
            "- **`Emma AI` is never translated.** It is a product name.",
            "- **Rank/shift/leave codes keep their code in brackets** - `健康護理員（HCA）` -",
            "  so a bilingual floor can still match the label to the paper roster. Codes are",
            "  never shown bare in Chinese: an untranslated `HCA` is what a browser's",
            "  auto-translate rendered as 氫氯噻嗪 (hydrochlorothiazide).",
            "",
        ]
        current = None
        for section, key, en, zh in rows:
            if section != current:
                current = section
                lines.extend(["", f"## {section}", "",
                              "| key | English | 中文 |", "|---|---|---|"])
            lines.append(f"| `{key}` | {en} | {zh} |")
        lines.append("")
        out.write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote {out.relative_to(ROOT)} ({len(rows)} strings)")


if __name__ == "__main__":
    main()
