"""Verify an inference profile in the actual AWS account; synthetic invocation is opt-in."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from emma_core.config import settings
from emma_core.services.ai_gateway import BedrockProvider, ProviderError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="AWS CLI profile, including an SSO profile")
    parser.add_argument("--region", default=settings.bedrock_region)
    parser.add_argument("--model", default=settings.bedrock_model_id)
    parser.add_argument("--invoke", action="store_true")
    args = parser.parse_args()
    if not args.region:
        parser.error("set --region to a supported Bedrock source region")
    if args.profile:
        boto3.setup_default_session(profile_name=args.profile)
    try:
        profile = boto3.client("bedrock", region_name=args.region).get_inference_profile(
            inferenceProfileIdentifier=args.model
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"AccessDenied", "AccessDeniedException"} or not args.invoke:
            raise
        print(json.dumps({
            "profile_verified": False,
            "warning": "GetInferenceProfile denied; attempting the requested invocation only.",
        }))
    else:
        print(
            json.dumps(
                {
                    "profile_id": profile.get("inferenceProfileId"),
                    "status": profile.get("status"),
                    "source_region": args.region,
                    "destination_regions": sorted(
                        {row["modelArn"].split(":")[3] for row in profile.get("models", [])}
                    ),
                },
                indent=2,
            )
        )
    if args.invoke:
        provider = BedrockProvider(region=args.region, model=args.model)
        answer = provider.complete(
            system='Return JSON: {"ok": true}.',
            prompt="Synthetic connectivity check. No personal data.",
            max_tokens=100,
        )
        body = json.loads(answer)
        if body.get("ok") is not True:
            raise RuntimeError("model did not return the expected connectivity result")
        print(
            json.dumps({"invocation_passed": True, **provider.last_metrics}, indent=2)
        )


if __name__ == "__main__":
    try:
        main()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "AWS error")
        sys.exit(f"Bedrock verification failed: {code}. Check account access and IAM permissions.")
    except BotoCoreError as exc:
        sys.exit(
            f"AWS authentication or connection unavailable ({type(exc).__name__}). "
            "Configure an AWS profile and sign in before retrying."
        )
    except ProviderError as exc:
        sys.exit(f"Bedrock invocation failed: {exc}")
