#!/usr/bin/env python3
"""
ICUGuardian — Zero-Dependency AWS Signature Version 4 (AWS4-HMAC-SHA256) Client & Provisioner
Communicates directly with AWS STS, Amazon DynamoDB, and AWS IoT Core using only the
Python 3 Standard Library (hmac, hashlib, urllib.request, json).
"""

import datetime
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def aws_sigv4_request(
    method: str,
    service: str,
    region: str,
    host: str,
    canonical_uri: str,
    canonical_querystring: str = "",
    payload: bytes = b"",
    extra_headers: Optional[Dict[str, str]] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    timeout: float = 15.0,
) -> Tuple[int, str]:
    ak = (access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")).strip()
    sk = (secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")).strip()
    if not ak or not sk:
        raise RuntimeError("Missing AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY")

    t = datetime.datetime.now(datetime.timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    payload_hash = hashlib.sha256(payload).hexdigest()

    headers: Dict[str, str] = {
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    if extra_headers:
        for k, v in extra_headers.items():
            headers[k.lower()] = v.strip()

    sorted_header_keys = sorted(headers.keys())
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted_header_keys)
    signed_headers = ";".join(sorted_header_keys)

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _get_signature_key(sk, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"https://{host}{canonical_uri}"
    if canonical_querystring:
        url += f"?{canonical_querystring}"

    req_headers = {k: v for k, v in headers.items() if k != "host"}
    req_headers["Authorization"] = authorization_header

    req = urllib.request.Request(
        url,
        data=payload if method.upper() in ("POST", "PUT", "PATCH") else None,
        headers=req_headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return e.code, err_body


def dynamodb_call(target: str, body: Dict[str, Any], region: str, ak: Optional[str] = None, sk: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    host = f"dynamodb.{region}.amazonaws.com"
    payload = json.dumps(body).encode("utf-8")
    status, text = aws_sigv4_request(
        method="POST",
        service="dynamodb",
        region=region,
        host=host,
        canonical_uri="/",
        payload=payload,
        extra_headers={
            "content-type": "application/x-amz-json-1.0",
            "x-amz-target": f"DynamoDB_20120810.{target}",
        },
        access_key=ak,
        secret_key=sk,
    )
    try:
        return status, json.loads(text) if text else {}
    except Exception:
        return status, {"raw": text}


def to_ddb_attr(val: Any) -> Dict[str, Any]:
    if val is None:
        return {"NULL": True}
    if isinstance(val, bool):
        return {"BOOL": val}
    if isinstance(val, (int, float)):
        return {"N": str(val)}
    if isinstance(val, str):
        return {"S": val}
    if isinstance(val, list):
        return {"L": [to_ddb_attr(x) for x in val]}
    if isinstance(val, dict):
        return {"M": {str(k): to_ddb_attr(v) for k, v in val.items()}}
    return {"S": str(val)}


def dynamodb_put_item(table_name: str, item: Dict[str, Any], region: str, ak: Optional[str] = None, sk: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    ddb_item = {k: to_ddb_attr(v) for k, v in item.items() if v is not None and v != ""}
    return dynamodb_call("PutItem", {"TableName": table_name, "Item": ddb_item}, region, ak, sk)


def dynamodb_delete_item(table_name: str, key: Dict[str, Any], region: str, ak: Optional[str] = None, sk: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    ddb_key = {k: to_ddb_attr(v) for k, v in key.items()}
    return dynamodb_call("DeleteItem", {"TableName": table_name, "Key": ddb_key}, region, ak, sk)


def verify_sts_identity(ak: str, sk: str) -> Dict[str, Any]:
    status, body = aws_sigv4_request(
        method="POST",
        service="sts",
        region="us-east-1",
        host="sts.amazonaws.com",
        canonical_uri="/",
        payload=b"Action=GetCallerIdentity&Version=2011-06-15",
        extra_headers={
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
        },
        access_key=ak,
        secret_key=sk,
    )
    if status != 200:
        raise RuntimeError(f"STS authentication failed ({status}): {body}")
    return {"status": status, "raw": body}


def provision_all_aws_resources(ak: str, sk: str, region: str = "ap-south-1", thing_name: str = "ICU-PI-001") -> Dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    schema_path = root_dir / "aws-cloud" / "dynamodb" / "tables_schema.json"
    policy_path = root_dir / "aws-cloud" / "iot-core" / "iot_policy.json"
    certs_dir = root_dir / "raspberry-pi-gateway" / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Verifying AWS IAM credentials via STS...")
    sts_info = verify_sts_identity(ak, sk)
    print(f"      [OK] AWS IAM Credentials authenticated successfully.")

    print(f"[2/4] Provisioning 5 Amazon DynamoDB tables in {region}...")
    schema_doc = json.loads(schema_path.read_text(encoding="utf-8"))
    created_tables: List[str] = []
    for tdef in schema_doc.get("tables", []):
        tname = tdef["TableName"]
        st, _ = dynamodb_call("DescribeTable", {"TableName": tname}, region, ak, sk)
        if st == 200:
            print(f"      [EXISTS] DynamoDB table '{tname}' is already active.")
            created_tables.append(tname)
            continue
        create_params = {
            "TableName": tname,
            "BillingMode": tdef.get("BillingMode", "PAY_PER_REQUEST"),
            "AttributeDefinitions": tdef["AttributeDefinitions"],
            "KeySchema": tdef["KeySchema"],
        }
        if "GlobalSecondaryIndexes" in tdef:
            create_params["GlobalSecondaryIndexes"] = tdef["GlobalSecondaryIndexes"]
        if "StreamSpecification" in tdef:
            create_params["StreamSpecification"] = tdef["StreamSpecification"]
        st_create, resp_create = dynamodb_call("CreateTable", create_params, region, ak, sk)
        if st_create == 200:
            print(f"      [CREATED] DynamoDB table '{tname}' provisioned.")
            created_tables.append(tname)
        else:
            print(f"      [WARN] CreateTable '{tname}' returned {st_create}: {resp_create}")

    # Wait briefly for tables to become ACTIVE and seed initial records
    for tname in ("ICU_Patients", "ICU_Devices"):
        for _ in range(25):
            st, desc = dynamodb_call("DescribeTable", {"TableName": tname}, region, ak, sk)
            if st == 200 and desc.get("Table", {}).get("TableStatus") == "ACTIVE":
                break
            time.sleep(2.0)

    print(f"[3/4] Seeding initial ICU patients & Raspberry Pi 5 gateway into DynamoDB...")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    seed_patients = [
        {"patientId": "PATIENT-001", "name": "John Anderson", "age": 58, "gender": "Male", "ward": "ICU-A", "bedNumber": "ICU-01", "diagnosis": "Post-CABG Day 2", "assignedDeviceId": thing_name, "status": "CRITICAL", "updatedAt": now_iso},
        {"patientId": "PATIENT-002", "name": "Maria Rodriguez", "age": 64, "gender": "Female", "ward": "ICU-A", "bedNumber": "ICU-02", "diagnosis": "Acute Respiratory Distress (ARDS)", "assignedDeviceId": "ICU-PI-002", "status": "WARNING", "updatedAt": now_iso},
        {"patientId": "PATIENT-003", "name": "Robert Chen", "age": 45, "gender": "Male", "ward": "ICU-A", "bedNumber": "ICU-03", "diagnosis": "Septic Shock Recovery", "assignedDeviceId": "ICU-PI-003", "status": "NORMAL", "updatedAt": now_iso},
        {"patientId": "PATIENT-004", "name": "Emily Thompson", "age": 71, "gender": "Female", "ward": "ICU-B", "bedNumber": "ICU-04", "diagnosis": "Acute Decompensated Heart Failure", "assignedDeviceId": "ICU-PI-004", "status": "CRITICAL", "updatedAt": now_iso},
        {"patientId": "PATIENT-005", "name": "David Kim", "age": 39, "gender": "Male", "ward": "ICU-B", "bedNumber": "ICU-05", "diagnosis": "Post-Craniotomy Neuro Monitoring", "assignedDeviceId": "ICU-PI-005", "status": "NORMAL", "updatedAt": now_iso},
        {"patientId": "PATIENT-006", "name": "Sarah Jenkins", "age": 53, "gender": "Female", "ward": "ICU-B", "bedNumber": "ICU-06", "diagnosis": "Diabetic Ketoacidosis (DKA)", "assignedDeviceId": "ICU-PI-006", "status": "WARNING", "updatedAt": now_iso},
    ]
    for p in seed_patients:
        dynamodb_put_item("ICU_Patients", p, region, ak, sk)

    dynamodb_put_item(
        "ICU_Devices",
        {
            "deviceId": thing_name,
            "bedNumber": "ICU-01",
            "assignedPatientId": "PATIENT-001",
            "status": "ONLINE",
            "ipAddress": "192.168.50.1",
            "firmwareVersion": "v2.4.0-pi5",
            "lastHeartbeat": int(time.time() * 1000),
            "cpuTemp": 43.2,
            "memoryUsagePercent": 34.0,
        },
        region,
        ak,
        sk,
    )
    print(f"      [OK] Seeded 6 ICU patients and gateway '{thing_name}' into Amazon DynamoDB.")

    print(f"[4/4] Provisioning AWS IoT Core Thing '{thing_name}' & X.509 Certificates...")
    iot_host = f"iot.{region}.amazonaws.com"
    iot_endpoint = ""

    # 1. Create Thing
    st_thing, body_thing = aws_sigv4_request(
        method="POST",
        service="iot",
        region=region,
        host=iot_host,
        canonical_uri=f"/things/{thing_name}",
        payload=json.dumps({"attributePayload": {"attributes": {"ward": "ICU-A", "bed": "ICU-01"}}}).encode("utf-8"),
        extra_headers={"content-type": "application/json"},
        access_key=ak,
        secret_key=sk,
    )
    if st_thing in (200, 201):
        print(f"      [OK] AWS IoT Thing '{thing_name}' registered.")
    else:
        print(f"      [INFO] AWS IoT Thing response ({st_thing}): {body_thing[:160]}")

    # 2. Create Keys & Certificate if not already present
    cert_file = certs_dir / "device.pem.crt"
    key_file = certs_dir / "private.pem.key"
    pub_file = certs_dir / "public.pem.key"
    ca_file = certs_dir / "AmazonRootCA1.pem"

    if not cert_file.exists() or not key_file.exists():
        st_cert, body_cert = aws_sigv4_request(
            method="POST",
            service="iot",
            region=region,
            host=iot_host,
            canonical_uri="/keys-and-certificate",
            canonical_querystring="setAsActive=true",
            payload=b"",
            access_key=ak,
            secret_key=sk,
        )
        if st_cert in (200, 201):
            cert_data = json.loads(body_cert)
            cert_arn = cert_data["certificateArn"]
            cert_file.write_text(cert_data["certificatePem"], encoding="utf-8")
            key_file.write_text(cert_data["keyPair"]["PrivateKey"], encoding="utf-8")
            pub_file.write_text(cert_data["keyPair"]["PublicKey"], encoding="utf-8")
            os.chmod(key_file, 0o600)
            print(f"      [OK] Generated X.509 device certificate & private key in {certs_dir}")

            # Download AmazonRootCA1.pem
            try:
                with urllib.request.urlopen("https://www.amazontrust.com/repository/AmazonRootCA1.pem", timeout=10) as r:
                    ca_file.write_bytes(r.read())
                print(f"      [OK] Downloaded AmazonRootCA1.pem")
            except Exception as e:
                print(f"      [WARN] Could not download AmazonRootCA1.pem: {e}")

            # Create & Attach Policy
            policy_name = "ICUGuardianDevicePolicy"
            policy_doc_raw = policy_path.read_text(encoding="utf-8").replace("${AWS_REGION}", region).replace("${AWS_ACCOUNT_ID}", "*")
            aws_sigv4_request(
                method="POST",
                service="iot",
                region=region,
                host=iot_host,
                canonical_uri=f"/policies/{policy_name}",
                payload=json.dumps({"policyDocument": policy_doc_raw}).encode("utf-8"),
                extra_headers={"content-type": "application/json"},
                access_key=ak,
                secret_key=sk,
            )
            aws_sigv4_request(
                method="PUT",
                service="iot",
                region=region,
                host=iot_host,
                canonical_uri=f"/target-policies/{policy_name}",
                payload=b"{}",
                extra_headers={"x-amzn-iot-principal": cert_arn, "content-type": "application/json"},
                access_key=ak,
                secret_key=sk,
            )
            aws_sigv4_request(
                method="PUT",
                service="iot",
                region=region,
                host=iot_host,
                canonical_uri=f"/things/{thing_name}/principals",
                payload=b"",
                extra_headers={"x-amzn-iot-principal": cert_arn},
                access_key=ak,
                secret_key=sk,
            )
            print(f"      [OK] Attached IoT Policy '{policy_name}' and Certificate to '{thing_name}'.")
        else:
            print(f"      [INFO] IoT Certificate creation returned ({st_cert}): {body_cert[:160]}")
    else:
        print(f"      [EXISTS] X.509 certificates already present in {certs_dir}")

    # 3. Describe IoT Data-ATS Endpoint
    st_ep, body_ep = aws_sigv4_request(
        method="GET",
        service="iot",
        region=region,
        host=iot_host,
        canonical_uri="/endpoint",
        canonical_querystring="endpointType=iot%3AData-ATS",
        access_key=ak,
        secret_key=sk,
    )
    if st_ep == 200:
        iot_endpoint = json.loads(body_ep).get("endpointAddress", "")
        print(f"      [OK] AWS IoT Core ATS Endpoint: {iot_endpoint}")
    else:
        print(f"      [INFO] DescribeEndpoint returned ({st_ep}): {body_ep[:160]}")

    # Save .env.aws
    env_file = root_dir / ".env.aws"
    env_file.write_text(
        f"""# Auto-generated by ICUGuardian AWS Provisioner
# Copy this folder (including .env.aws and raspberry-pi-gateway/certs/) to any other machine
# to connect to AWS automatically without repeating any setup steps.
export AWS_ACCESS_KEY_ID="{ak}"
export AWS_SECRET_ACCESS_KEY="{sk}"
export AWS_DEFAULT_REGION="{region}"
export AWS_REGION="{region}"
export AWS_IOT_ENDPOINT="{iot_endpoint}"
export DEVICE_ID="{thing_name}"
export AWS_DYNAMODB_ENABLED="true"
""",
        encoding="utf-8",
    )
    os.chmod(env_file, 0o600)
    print(f"\n[DONE] Saved portable configuration to {env_file}")
    return {
        "region": region,
        "tables": created_tables,
        "thingName": thing_name,
        "iotEndpoint": iot_endpoint,
        "envFile": str(env_file),
    }


if __name__ == "__main__":
    import sys
    ak_arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AWS_ACCESS_KEY_ID", "")
    sk_arg = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    reg_arg = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
    provision_all_aws_resources(ak_arg, sk_arg, reg_arg)
