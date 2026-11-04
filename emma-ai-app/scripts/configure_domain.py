"""Connect an Amplify subdomain to GoDaddy. Preview by default; --apply writes."""

from __future__ import annotations

import argparse
import os
import re

import boto3
import requests


def dns_records(association: dict, domain: str) -> list[dict]:
    records = []
    values = [association.get("certificateVerificationDNSRecord")]
    values += [row.get("dnsRecord") for row in association.get("subDomains", [])]
    for value in values:
        if not value:
            continue
        parts = value.split()
        if len(parts) != 3 or parts[1].upper() != "CNAME":
            raise ValueError(
                "AWS returned an unsupported DNS record; review it manually"
            )
        host, _, target = parts
        host = host.rstrip(".")
        if host.endswith("." + domain):
            host = host[: -(len(domain) + 1)]
        elif host == domain:
            raise ValueError("apex-domain routing requires a separate DNS plan")
        elif "." in host:
            raise ValueError("AWS returned a DNS record outside the selected domain")
        records.append(
            {"type": "CNAME", "name": host, "data": target.rstrip("."), "ttl": 600}
        )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--subdomain", default="www")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--godaddy", action="store_true")
    args = parser.parse_args()
    domain = args.domain.lower().strip().rstrip(".")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", domain):
        parser.error("provide a valid domain without a URL or path")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", args.subdomain):
        parser.error("provide a single subdomain label; apex routing is not automated")
    key, secret = os.getenv("GODADDY_API_KEY"), os.getenv("GODADDY_API_SECRET")
    if args.apply and args.godaddy and (not key or not secret):
        parser.error("GoDaddy API credentials are required in the environment")
    client = boto3.client("amplify", region_name=args.region)
    try:
        association = client.get_domain_association(
            appId=args.app_id, domainName=domain
        )["domainAssociation"]
    except client.exceptions.NotFoundException:
        if not args.apply:
            print(
                f"Preview: associate {args.subdomain}.{domain} with Amplify branch {args.branch}"
            )
            print(
                "Run with --apply to create the association, then review the returned DNS records"
            )
            return
        association = client.create_domain_association(
            appId=args.app_id,
            domainName=domain,
            enableAutoSubDomain=False,
            subDomainSettings=[{"prefix": args.subdomain, "branchName": args.branch}],
        )["domainAssociation"]
    print("Amplify domain status:", association.get("domainStatus"))
    configured = [
        row.get("subDomainSetting") or {} for row in association.get("subDomains", [])
    ]
    if configured and not any(
        row.get("prefix") == args.subdomain and row.get("branchName") == args.branch
        for row in configured
    ):
        raise ValueError(
            "existing domain association does not match the requested branch and subdomain"
        )
    records = dns_records(association, domain)
    if not records:
        print(
            "DNS records are not available yet. Rerun after Amplify finishes preparing the certificate"
        )
        return
    for record in records:
        print(record["name"], record["type"], record["data"])
    if args.apply and args.godaddy:
        for record in records:
            response = requests.put(
                f"https://api.godaddy.com/v1/domains/{domain}/records/CNAME/{record['name']}",
                headers={"Authorization": f"sso-key {key}:{secret}"},
                json=[{"data": record["data"], "ttl": record["ttl"]}],
                timeout=20,
            )
            if response.status_code not in (200, 204):
                raise RuntimeError(
                    f"GoDaddy rejected a DNS update (HTTP {response.status_code})"
                )
        print(
            "Requested CNAME records were updated. Wait for DNS and Amplify certificate verification"
        )
    print(
        f"Add https://{args.subdomain}.{domain} to CORS_ORIGINS before using the custom domain"
    )


if __name__ == "__main__":
    main()
