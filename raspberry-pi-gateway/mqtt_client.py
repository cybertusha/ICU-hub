"""
AWS IoT Core MQTT over TLS v1.2 Client + Cloud Backend Bridge for Raspberry Pi Gateway.
- Uses X.509 mutual TLS authentication (device.pem.crt, private.pem.key, AmazonRootCA1.pem)
  when paho-mqtt and AWS IoT certificates are present.
- Also forwards MQTT envelopes to the Cloud Backend REST/WebSocket Ingestion endpoint
  so live demonstrations work seamlessly both with AWS IoT Core and in local/hybrid mode.
"""

import json
import os
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from config import (
    DEVICE_ID,
    DEVICE_NAME,
    FIRMWARE_VERSION,
    OPERATING_MODE,
    ASSIGNED_PATIENT_ID,
    AWS_IOT_ENDPOINT,
    AWS_IOT_PORT,
    AWS_IOT_ROOT_CA,
    AWS_IOT_CERT,
    AWS_IOT_PRIVATE_KEY,
    TOPIC_VITALS,
    TOPIC_STATUS,
    CLOUD_BACKEND_URL,
)
from logger import get_logger

log = get_logger("mqtt_client")


class AWSIoTMQTTClient:
    def __init__(self, device_id: str = DEVICE_ID):
        self.device_id = device_id
        self.paho_client = None
        self.tls_configured = False
        self.messages_published = 0
        self._init_paho_tls_if_available()

    def _init_paho_tls_if_available(self) -> None:
        """Initializes paho-mqtt with TLSv1.2 X.509 certificates if certs exist on disk."""
        certs_exist = (
            os.path.exists(AWS_IOT_ROOT_CA)
            and os.path.exists(AWS_IOT_CERT)
            and os.path.exists(AWS_IOT_PRIVATE_KEY)
        )
        if not certs_exist:
            log.info(
                "AWS IoT X.509 certificate files not found in certs/; using Cloud Backend MQTT-Bridge transport."
            )
            return

        try:
            import paho.mqtt.client as mqtt  # type: ignore

            client = mqtt.Client(client_id=self.device_id, protocol=mqtt.MQTTv311)
            # Configure MQTT Last Will and Testament (LWT)
            lwt_topic = TOPIC_STATUS.format(deviceId=self.device_id)
            lwt_payload = json.dumps(
                {
                    "deviceId": self.device_id,
                    "deviceStatus": "OFFLINE",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            client.will_set(lwt_topic, payload=lwt_payload, qos=1, retain=False)
            client.tls_set(
                ca_certs=AWS_IOT_ROOT_CA,
                certfile=AWS_IOT_CERT,
                keyfile=AWS_IOT_PRIVATE_KEY,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
            )
            client.connect_async(AWS_IOT_ENDPOINT, AWS_IOT_PORT, keepalive=45)
            client.loop_start()
            self.paho_client = client
            self.tls_configured = True
            log.info(f"Initialized AWS IoT Core MQTT over TLS client -> {AWS_IOT_ENDPOINT}:{AWS_IOT_PORT}")
        except Exception as exc:
            log.warning(f"Could not start paho-mqtt TLS client ({exc}); falling back to Cloud HTTP Bridge.")

    def publish_vitals(self, payload: Dict[str, Any]) -> bool:
        """
        Publishes validated vital reading to topic `icu/devices/{deviceId}/vitals`
        and delivers to the Cloud Backend processor.
        """
        dev_id = payload.get("deviceId") or self.device_id
        topic = TOPIC_VITALS.format(deviceId=dev_id)

        # 1. Publish to AWS IoT Core MQTT broker if TLS client is active
        if self.paho_client and self.tls_configured:
            try:
                self.paho_client.publish(topic, json.dumps(payload), qos=1)
            except Exception as exc:
                log.error(f"AWS IoT MQTT publish error on {topic}: {exc}")

        # 2. Deliver MQTT envelope to Cloud Backend (triggers process_vitals Lambda logic & WebSocket push)
        envelope = {
            "topic": topic,
            "qos": 1,
            "payload": payload,
        }
        data = json.dumps(envelope).encode("utf-8")
        req = urllib.request.Request(
            f"{CLOUD_BACKEND_URL}/api/iot/ingest-vitals",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if 200 <= resp.status < 300:
                    self.messages_published += 1
                    return True
                return False
        except Exception as exc:
            log.warning(f"Cloud ingestion endpoint unreachable ({exc})")
            return False

    def publish_device_status(
        self,
        device_status: str = "ONLINE",
        offline_queue_size: int = 0,
        device_id: Optional[str] = None,
    ) -> bool:
        """Publishes gateway connectivity heartbeat to `icu/devices/{deviceId}/status`."""
        target_id = device_id or self.device_id
        topic = TOPIC_STATUS.format(deviceId=target_id)
        status_payload = {
            "deviceId": target_id,
            "deviceName": DEVICE_NAME if target_id == DEVICE_ID else f"{target_id} Monitor Hub",
            "deviceStatus": device_status,
            "offlineQueueSize": offline_queue_size,
            "firmwareVersion": FIRMWARE_VERSION,
            "operatingMode": OPERATING_MODE,
            "assignedPatientId": ASSIGNED_PATIENT_ID,
            "lastSeen": datetime.now(timezone.utc).isoformat(),
        }

        if self.paho_client and self.tls_configured:
            try:
                self.paho_client.publish(topic, json.dumps(status_payload), qos=1)
            except Exception:
                pass

        data = json.dumps({"topic": topic, "payload": status_payload}).encode("utf-8")
        req = urllib.request.Request(
            f"{CLOUD_BACKEND_URL}/api/iot/device-status",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False
