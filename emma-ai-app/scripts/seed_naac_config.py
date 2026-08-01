"""Load NAAC TAH's configuration into a facility (MVP 2.2 / 2.3 / 4.1).

    python scripts/seed_naac_config.py                 # create/refresh, keep edits
    python scripts/seed_naac_config.py --overwrite     # let the sheet win
    python scripts/seed_naac_config.py --facility NAAC2

Separate from `seed.py` on purpose. That script builds the Home A / Home B demo
fixture and wipes those two facilities each run; this one loads a real home's real
configuration and never deletes anything. Running the demo seed must not be able
to take NAAC's dictionary with it.

Source files and what was left out: `docs/naac/README.md`.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from emma_core.db import get_service_client  # noqa: E402
from emma_core.services import naac_seed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility", default=naac_seed.FACILITY_CODE,
                        help="facilities.code to load into (default: NAAC)")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace values a facility has since edited by hand")
    args = parser.parse_args()

    client = get_service_client()
    try:
        result = naac_seed.provision(
            client, facility_code=args.facility, overwrite=args.overwrite)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"NAAC configuration loaded into {result['facility_code']} "
          f"({result['facility_id']})")
    print(f"  facility configs   {result['configs']:>4}")
    print(f"  shift definitions  {result['shift_definitions']:>4}")
    print(f"  task definitions   {result['task_definitions']:>4}")
    print(f"  escort locations   {result['escort_locations']:>4}")
    if not args.overwrite:
        print("\nExisting rows were left alone. Re-run with --overwrite to let "
              "the source sheet win.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
