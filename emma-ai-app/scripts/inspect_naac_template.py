"""Describe a supplied workbook without printing staff names or roster cells."""

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.workbook.read_bytes()
    book = load_workbook(args.workbook, read_only=False, keep_links=False)
    result = {
        "template_sha256": hashlib.sha256(raw).hexdigest(),
        "sheet_names": book.sheetnames,
        "sheet_count": len(book.sheetnames),
        "layout": [
            {
                "sheet": s.title,
                "rows": s.max_row,
                "columns": s.max_column,
                "merged_ranges": [str(r) for r in s.merged_cells.ranges],
                "print_area": str(s.print_area),
            }
            for s in book
        ],
        "weeks": [],
        "summaries": [],
        "preserve_ranges": {},
        "metadata_cells": {},
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Inspected {len(book.sheetnames)} sheets; cell values were not included")


if __name__ == "__main__":
    main()
