from __future__ import annotations

import logging
from typing import Any

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {"status", "list_regions", "describe_instances", "list_buckets", "sts_identity"}


class AWSTool(BaseTool):
    name = "aws"
    description = (
        "Call read-only AWS APIs using instance role or configured credentials. "
        "Actions: status, sts_identity, list_regions, describe_instances, list_buckets."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
            "region": {"type": "string"},
        },
        "required": ["action"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "status").lower()
        if action not in ALLOWED_ACTIONS:
            return ToolResult(success=False, output=f"Action not allowed: {action}")

        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError:
            return ToolResult(success=False, output="boto3 is not installed")

        settings = get_settings()
        region = kwargs.get("region") or settings.aws_region

        try:
            if action == "status":
                session = boto3.Session(region_name=region)
                creds = session.get_credentials()
                if creds is None:
                    return ToolResult(success=False, output="No AWS credentials available (set IAM role or env keys)")
                return ToolResult(
                    success=True,
                    output=f"AWS credentials available in region {region}",
                    data={"region": region, "method": creds.method},
                )

            if action == "sts_identity":
                sts = boto3.client("sts", region_name=region)
                ident = sts.get_caller_identity()
                return ToolResult(
                    success=True,
                    output=f"Account={ident.get('Account')} Arn={ident.get('Arn')}",
                    data=ident,
                )

            if action == "list_regions":
                ec2 = boto3.client("ec2", region_name=region)
                regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]
                return ToolResult(success=True, output="\n".join(regions), data={"regions": regions})

            if action == "describe_instances":
                ec2 = boto3.client("ec2", region_name=region)
                resp = ec2.describe_instances(MaxResults=20)
                lines = []
                for res in resp.get("Reservations", []):
                    for inst in res.get("Instances", []):
                        lines.append(
                            f"{inst.get('InstanceId')}  {inst.get('State', {}).get('Name')}  "
                            f"{inst.get('InstanceType')}  {inst.get('PrivateIpAddress')}"
                        )
                return ToolResult(success=True, output="\n".join(lines) or "(none)", data={"count": len(lines)})

            if action == "list_buckets":
                s3 = boto3.client("s3", region_name=region)
                buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
                return ToolResult(success=True, output="\n".join(buckets) or "(none)", data={"buckets": buckets})

            return ToolResult(success=False, output=f"Unknown action: {action}")
        except (BotoCoreError, ClientError) as exc:
            return ToolResult(success=False, output=f"AWS error: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AWS tool failed: %s", exc)
            return ToolResult(success=False, output=f"AWS tool failed: {exc}")
