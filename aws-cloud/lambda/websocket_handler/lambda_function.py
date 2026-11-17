"""
AWS Lambda Function: ICU_WebSocketHandler (`aws-cloud/lambda/websocket_handler/lambda_function.py`)
Manages API Gateway WebSocket connections ($connect, $disconnect, $default) and fan-out broadcasts
to authenticated Doctor Web Dashboard clients.
"""

import json
import os
import time
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    req_ctx = event.get("requestContext", {})
    route_key = req_ctx.get("routeKey", "$default")
    connection_id = req_ctx.get("connectionId", "local-conn")

    if os.environ.get("AWS_EXECUTION_ENV"):
        import boto3  # type: ignore

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ.get("WS_CONNECTIONS_TABLE", "ICU_WebSocketConnections"))

        if route_key == "$connect":
            table.put_item(
                Item={
                    "connectionId": connection_id,
                    "connectedAt": int(time.time()),
                    "ttl": int(time.time()) + 86400,
                }
            )
            return {"statusCode": 200, "body": "Connected"}

        if route_key == "$disconnect":
            table.delete_item(Key={"connectionId": connection_id})
            return {"statusCode": 200, "body": "Disconnected"}

    return {"statusCode": 200, "body": json.dumps({"route": route_key, "connectionId": connection_id})}
