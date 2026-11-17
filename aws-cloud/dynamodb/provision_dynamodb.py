#!/usr/bin/env python3
"""
Amazon DynamoDB Table Provisioner & Initial Demo Data Seeder (`aws-cloud/dynamodb/provision_dynamodb.py`).
Reads `tables_schema.json` and provisions all required DynamoDB tables in AWS (or LocalStack DynamoDB).
"""

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "tables_schema.json"


def load_table_definitions() -> list:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["tables"]


def provision_tables(endpoint_url: str = None, region: str = "us-east-1") -> None:
    import boto3  # type: ignore

    dynamodb = boto3.client("dynamodb", region_name=region, endpoint_url=endpoint_url)
    existing = dynamodb.list_tables().get("TableNames", [])

    for tdef in load_table_definitions():
        name = tdef["TableName"]
        if name in existing:
            print(f"  [SKIP] DynamoDB Table '{name}' already exists.")
            continue

        create_kwargs = {
            "TableName": name,
            "BillingMode": tdef["BillingMode"],
            "KeySchema": tdef["KeySchema"],
            "AttributeDefinitions": tdef["AttributeDefinitions"],
        }
        if "GlobalSecondaryIndexes" in tdef:
            create_kwargs["GlobalSecondaryIndexes"] = tdef["GlobalSecondaryIndexes"]

        dynamodb.create_table(**create_kwargs)
        print(f"  [CREATED] DynamoDB Table '{name}'")


if __name__ == "__main__":
    tables = load_table_definitions()
    print(f"Loaded {len(tables)} DynamoDB table definitions from {SCHEMA_PATH.name}:")
    for t in tables:
        print(f"  - {t['TableName']} (Keys: {[k['AttributeName'] for k in t['KeySchema']]})")
    if "--apply" in sys.argv:
        provision_tables(
            endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL"),
            region=os.environ.get("AWS_REGION", "us-east-1"),
        )
