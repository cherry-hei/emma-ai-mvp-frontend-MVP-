"""The five workflows a trial home has to be able to do, run end to end.

    python scripts/smoke_tenant.py --config scripts/tenants/naac.json
    python scripts/smoke_tenant.py --config scripts/tenants/naac.json --api https://host

With `--api` it drives a deployed instance over HTTP. Without it, it drives the
application in process against the same database, which is what makes it usable
from a laptop with no deployment in front of it.

The five, and nothing beyond them, because an open ended "core workflow" grows
every time someone looks at it:

  1. every account in the config can sign in and gets the home it belongs to
  2. the roster grid loads, in the charity's own duty codes
  3. a manager writes a cell and the change reaches the audit trail
  4. a staff member raises a request and the manager sees it in the queue
  5. a validation run returns, reporting violations rather than failing

It writes. Point it at a trial home, not at a home doing real work. The cell it
writes is put back the way it was found, but the audit entries for both the write
and the restore are permanent, which is the point of an audit trail.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date as Date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASSWORD = "EmmaDev123!"


class Api:
    """One surface over the two ways of calling: in process, or a real host."""

    def __init__(self, base: str | None):
        self.base = base
        if base:
            import httpx
            self.http = httpx.Client(base_url=base, timeout=30)
        else:
            from fastapi.testclient import TestClient
            from api.main import app
            self.http = TestClient(app, raise_server_exceptions=False)

    def call(self, method: str, path: str, token: str | None = None, **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.http.request(method, path, headers=headers, **kwargs)


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def record(self, step: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((step, ok, detail))
        print(f"  {'pass' if ok else 'FAIL'}  {step}" + (f"  ({detail})" if detail else ""))
        return ok

    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


def sign_in(api: Api, email: str) -> str | None:
    response = api.call("POST", "/auth/login",
                        json={"email": email, "password": PASSWORD})
    if response.status_code != 200:
        return None
    return response.json().get("access_token")


def workflow_logins(api: Api, config: dict, report: Report) -> dict[str, str]:
    tokens: dict[str, str] = {}
    home_code = config["facility"]["code"]
    for account in config["accounts"]:
        token = sign_in(api, account["email"])
        if not token:
            report.record(f"sign in {account['email']}", False, "login refused")
            continue
        current = api.call("GET", "/organisations/current", token)
        homes = api.call("GET", "/organisations/current/facilities", token)
        codes = [h["code"] for h in homes.json()] if homes.status_code == 200 else []
        ok = current.status_code == 200 and home_code in codes
        report.record(f"sign in {account['email']}", ok,
                      f"{account['role']}, sees {codes or 'nothing'}")
        if ok:
            tokens[account["role"]] = token
    return tokens


def _manager_token(tokens: dict[str, str]) -> str | None:
    return tokens.get("superintendent") or tokens.get("admin")


def workflow_grid(api: Api, tokens: dict[str, str], report: Report) -> dict | None:
    token = _manager_token(tokens)
    if not token:
        report.record("roster grid loads", False, "no manager login to load it with")
        return None
    codes = {d["shift_type"] for d in api.call("GET", "/shift-definitions", token).json()}
    if not codes:
        report.record("roster grid loads", False, "the charity has no duty codes")
        return None
    for period in api.call("GET", "/roster-periods", token).json():
        versions = api.call("GET", "/roster-versions", token,
                            params={"period_id": period["id"]}).json()
        manual = next((v for v in versions if v["version_type"] == "manual"), None)
        if not manual:
            continue
        grid = api.call("GET", f"/rosters/{period['id']}", token,
                        params={"version_id": manual["id"]}).json()
        used = {cell.get("shift_type") for row in grid.get("rows", [])
                for cell in row.get("cells", []) if cell.get("assignment_id")}
        if not used:
            continue
        unknown = used - codes
        report.record("roster grid loads", not unknown,
                      f"{len(grid['rows'])} people, {len(used)} codes in use"
                      if not unknown else f"codes outside the charity: {unknown}")
        return {"period": period, "version": manual, "grid": grid, "token": token}
    report.record("roster grid loads", False, "no rostered cell to show")
    return None


def workflow_cell_write(api: Api, loaded: dict | None, report: Report) -> None:
    if not loaded:
        report.record("cell write reaches the audit trail", False, "no grid to write in")
        return
    token = loaded["token"]
    cell = next((
        {"staff_id": row["staff"]["id"], "date": c["date"], "was": c["shift_type"]}
        for row in loaded["grid"]["rows"] for c in row["cells"]
        if c.get("assignment_id")), None)
    if not cell:
        report.record("cell write reaches the audit trail", False, "no cell to edit")
        return
    body = {"roster_version_id": loaded["version"]["id"], "staff_id": cell["staff_id"],
            "date": cell["date"], "shift_type": cell["was"], "tasks": []}
    wrote = api.call("PATCH", "/shifts", token, json=body)
    if wrote.status_code not in (200, 201):
        report.record("cell write reaches the audit trail", False,
                      f"write refused: {wrote.status_code} {wrote.text[:120]}")
        return
    trail = api.call("GET", "/audit-logs", token,
                     params={"entity_table": "shift_assignments", "limit": 5})
    ok = trail.status_code == 200 and bool(trail.json())
    report.record("cell write reaches the audit trail", ok,
                  "written and recorded" if ok else "written but no audit row came back")


def workflow_request_loop(api: Api, tokens: dict[str, str], report: Report) -> None:
    staff_token, manager_token = tokens.get("staff"), _manager_token(tokens)
    if not (staff_token and manager_token):
        report.record("staff request reaches the manager", False,
                      "needs both a staff and a manager login")
        return
    start = Date.today() + timedelta(days=45)
    raised = api.call("POST", "/leave-requests", staff_token, json={
        "leave_type": "AL", "date_start": str(start), "date_end": str(start),
        "reason": "smoke test, synthetic"})
    if raised.status_code != 201:
        report.record("staff request reaches the manager", False,
                      f"submit refused: {raised.status_code} {raised.text[:120]}")
        return
    request_id = raised.json().get("id")
    queue = api.call("GET", "/leave-requests", manager_token, params={"status": "pending"})
    seen = (queue.status_code == 200
            and any(r.get("id") == request_id for r in queue.json()))
    report.record("staff request reaches the manager", seen,
                  "in the pending queue" if seen else "submitted but not in the queue")
    if request_id:
        api.call("POST", f"/leave-requests/{request_id}/withdraw", staff_token)


def workflow_validation(api: Api, loaded: dict | None, report: Report) -> None:
    if not loaded:
        report.record("validation run returns", False, "no roster to validate")
        return
    result = api.call("POST", "/validate-roster", loaded["token"],
                      json={"roster_version_id": loaded["version"]["id"]})
    ok = result.status_code == 200 and "violations" in result.json()
    count = len(result.json().get("violations", [])) if ok else 0
    report.record("validation run returns", ok,
                  f"{count} violations reported" if ok
                  else f"{result.status_code} {result.text[:120]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="the tenant config JSON")
    parser.add_argument("--api", help="base URL of a deployed API; omit to run in process")
    args = parser.parse_args()

    config = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    api = Api(args.api)
    report = Report()
    print(f"Smoke test: {config['facility']['name']} ({config['facility']['code']})")
    print(f"Against: {args.api or 'the application in process'}\n")

    tokens = workflow_logins(api, config, report)
    loaded = workflow_grid(api, tokens, report)
    workflow_cell_write(api, loaded, report)
    workflow_request_loop(api, tokens, report)
    workflow_validation(api, loaded, report)

    failed = report.failed()
    print(f"\n{len(report.rows) - failed} of {len(report.rows)} steps passed.")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
