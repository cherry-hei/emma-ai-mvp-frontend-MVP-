"""Record the 13 backend cases. Live model scoring remains a separate UAT step."""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    junit = args.output.with_suffix(".xml")
    app = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_ai_acceptance.py",
            "-q",
            f"--junitxml={junit.resolve()}",
        ],
        cwd=app,
        check=False,
    )
    cases = []
    if junit.exists():
        for row in ET.parse(junit).iter("testcase"):
            cases.append(
                {
                    "case": row.attrib["name"].split("_")[1],
                    "backend_pass": not any(
                        child.tag in ("failure", "error", "skipped") for child in row
                    ),
                    "duration_seconds": float(row.attrib.get("time", 0)),
                    "human_model_score": None,
                }
            )
    args.output.write_text(
        json.dumps(
            {
                "kind": "backend_synthetic_verification",
                "live_model_invocation_verified": False,
                "cases": cases,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
