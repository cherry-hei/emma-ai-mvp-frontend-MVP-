"""Check deployed API, browser CORS and both user interfaces without changing data."""

import argparse
import json
from urllib.parse import urlparse

import httpx


def check(api: str, manager: str, staff: str) -> list[dict]:
    rows = []
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for label, url in (
            ("API health", api.rstrip("/") + "/health"),
            ("OpenAPI", api.rstrip("/") + "/openapi.json"),
            ("Manager UI", manager),
            ("Staff UI", staff),
        ):
            try:
                response = client.get(url)
                ok = (
                    response.status_code == 200
                    and urlparse(str(response.url)).scheme == "https"
                )
                if label == "OpenAPI" and ok:
                    paths = response.json().get("paths", {})
                    ok = all(
                        path in paths
                        for path in (
                            "/ai/compliance-qa",
                            "/facility-events",
                            "/exports/naac/tahduty.xlsx",
                        )
                    )
                rows.append(
                    {"check": label, "pass": ok, "http_status": response.status_code}
                )
            except (httpx.HTTPError, ValueError) as exc:
                rows.append(
                    {"check": label, "pass": False, "error": type(exc).__name__}
                )
        for label, url in (("Manager CORS", manager), ("Staff CORS", staff)):
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            try:
                response = client.options(
                    api.rstrip("/") + "/auth/login",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type,authorization",
                    },
                )
                rows.append(
                    {
                        "check": label,
                        "pass": response.status_code == 200
                        and response.headers.get("access-control-allow-origin")
                        == origin,
                    }
                )
            except httpx.HTTPError as exc:
                rows.append(
                    {"check": label, "pass": False, "error": type(exc).__name__}
                )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--manager", required=True)
    parser.add_argument("--staff", required=True)
    args = parser.parse_args()
    rows = check(args.api, args.manager, args.staff)
    print(json.dumps(rows, indent=2))
    raise SystemExit(0 if all(row["pass"] for row in rows) else 1)


if __name__ == "__main__":
    main()
