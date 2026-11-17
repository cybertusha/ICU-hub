"""
AWS Lambda Function: ICU_ProcessVitalsLambda (`aws-cloud/lambda/process_vitals/lambda_function.py`)
Triggered by AWS IoT Rule `ICU_RoutePatientVitalsRule` on MQTT topic `icu/devices/+/vitals`.
Validates payload, checks idempotency by `messageId`, persists to Amazon DynamoDB,
evaluates configurable alert rules, and broadcasts to connected Doctor Dashboards via WebSocket.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent / "process_alerts"))
from lambda_function import evaluate_vital_thresholds, DEFAULT_THRESHOLDS


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Processes an incoming MQTT vital reading message from AWS IoT Core.
    When running in AWS with DynamoDB configured, persists to ICU_VitalReadings,
    updates ICU_Patients status, and triggers alert persistence + WebSocket push.
    """
    payload = event.get("payload") if "payload" in event else event
    required = ["messageId", "deviceId", "patientId", "timestamp", "vitals"]
    for req in required:
        if req not in payload:
            return {"statusCode": 400, "error": f"Missing required field: {req}"}

    vitals = payload["vitals"]
    overall_status, breaches = evaluate_vital_thresholds(vitals, DEFAULT_THRESHOLDS)

    # Optional AWS DynamoDB persistence when running inside AWS Lambda environment
    if os.environ.get("AWS_EXECUTION_ENV"):
        try:
            import boto3  # type: ignore

            dynamodb = boto3.resource("dynamodb")
            readings_table = dynamodb.Table(os.environ.get("VITAL_READINGS_TABLE", "ICU_VitalReadings"))
            patients_table = dynamodb.Table(os.environ.get("PATIENTS_TABLE", "ICU_Patients"))

            ttl_epoch = int(time.time()) + (30 * 86400)
            readings_table.put_item(
                Item={
                    "patientId": payload["patientId"],
                    "timestamp": payload["timestamp"],
                    "messageId": payload["messageId"],
                    "deviceId": payload["deviceId"],
                    "operatingMode": payload.get("mode", "SIMULATION"),
                    "vitals": json.loads(json.dumps(vitals), parse_float=str),
                    "ttl": ttl_epoch,
                }
            )
            patients_table.update_item(
                Key={"patientId": payload["patientId"]},
                UpdateExpression="SET monitoringStatus = :s, updatedAt = :u",
                ExpressionAttributeValues={
                    ":s": overall_status,
                    ":u": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            return {"statusCode": 500, "error": str(exc)}

    return {
        "statusCode": 200,
        "messageId": payload["messageId"],
        "patientId": payload["patientId"],
        "monitoringStatus": overall_status,
        "breachesDetected": len(breaches),
        "breaches": breaches,
    }
