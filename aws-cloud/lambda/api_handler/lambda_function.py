"""
AWS Lambda Function: ICU_APIHandlerLambda (`aws-cloud/lambda/api_handler/lambda_function.py`)
Provides serverless REST API handling for Amazon API Gateway proxy integrations.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    path = event.get("path", "/api/health")
    method = event.get("httpMethod", "GET")
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(
            {
                "service": "ICU_APIHandlerLambda",
                "method": method,
                "path": path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
    }
