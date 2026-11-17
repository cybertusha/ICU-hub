"""
AWS Lambda Function: ICU_DeviceStatusLambda (`aws-cloud/lambda/device_status/lambda_function.py`)
Triggered by AWS IoT Rule `ICU_RouteDeviceStatusRule` on topic `icu/devices/+/status`
(including MQTT Last Will & Testament offline events).
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    payload = event.get("payload") if "payload" in event else event
    device_id = payload.get("deviceId")
    if not device_id:
        return {"statusCode": 400, "error": "Missing deviceId"}

    device_status = payload.get("deviceStatus", "ONLINE")
    now_iso = datetime.now(timezone.utc).isoformat()

    if os.environ.get("AWS_EXECUTION_ENV"):
        try:
            import boto3  # type: ignore

            dynamodb = boto3.resource("dynamodb")
            devices_table = dynamodb.Table(os.environ.get("DEVICES_TABLE", "ICU_Devices"))
            devices_table.update_item(
                Key={"deviceId": device_id},
                UpdateExpression="SET deviceStatus = :s, lastSeen = :ls, offlineQueueSize = :q",
                ExpressionAttributeValues={
                    ":s": device_status,
                    ":ls": now_iso,
                    ":q": int(payload.get("offlineQueueSize", 0)),
                },
            )
        except Exception as exc:
            return {"statusCode": 500, "error": str(exc)}

    return {
        "statusCode": 200,
        "deviceId": device_id,
        "deviceStatus": device_status,
        "updatedAt": now_iso,
    }
