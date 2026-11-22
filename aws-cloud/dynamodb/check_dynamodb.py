#!/usr/bin/env python3
"""
ICUGuardian — Zero-Dependency Amazon DynamoDB Live Table Inspector
Reads credentials from .env.aws (or environment variables) and prints live item counts
and sample records from your Amazon DynamoDB tables in ap-south-1.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "aws-cloud"))

from aws_sigv4 import dynamodb_call


def load_env_aws() -> None:
    env_file = ROOT_DIR / ".env.aws"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> None:
    load_env_aws()
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
    tables = [
        "ICU_Patients",
        "ICU_VitalReadings",
        "ICU_Alerts",
        "ICU_Devices",
        "ICU_ThresholdConfigurations",
        "ICU_Users",
        "ICU_WebSocketConnections",
    ]
    print("=" * 72)
    print(f"  ICUGuardian — Amazon DynamoDB Live Status (Region: {region})")
    print("=" * 72)
    for tname in tables:
        status, resp = dynamodb_call("Scan", {"TableName": tname, "Limit": 25}, region)
        if status == 200:
            count = resp.get("Count", 0)
            print(f"  [ACTIVE] {tname:<30} | Live Items (sample scan): {count}")
        else:
            print(f"  [ERROR]  {tname:<30} | HTTP {status}: {resp}")
    print("=" * 72)


if __name__ == "__main__":
    main()
