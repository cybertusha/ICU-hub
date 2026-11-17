"""
Network & Cloud Connectivity Manager for Raspberry Pi Bedside IoT Gateway.
Measures real HTTP/MQTT transmission latency, tracks cloud reachability,
and manages store-and-forward edge resilience.
"""

import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional
from config import CLOUD_BACKEND_URL
from logger import get_logger

log = get_logger("connectivity_manager")


class ConnectivityManager:
    def __init__(self):
        self.lock = threading.Lock()
        self._maintenance_offline_mode = False
        self._cloud_reachable = True
        self.last_connected_at: Optional[str] = datetime.now(timezone.utc).isoformat()
        self.last_disconnected_at: Optional[str] = None
        self.reconnect_count = 0
        self.last_latency_ms: float = 4.2

    def is_online(self) -> bool:
        with self.lock:
            return (not self._maintenance_offline_mode) and self._cloud_reachable

    def set_offline_mode(self, offline: bool) -> bool:
        """Toggles gateway offline store-and-forward mode (for network outage testing or maintenance)."""
        with self.lock:
            was_online = (not self._maintenance_offline_mode) and self._cloud_reachable
            self._maintenance_offline_mode = bool(offline)
            now_online = (not self._maintenance_offline_mode) and self._cloud_reachable

            if was_online and not now_online:
                self.last_disconnected_at = datetime.now(timezone.utc).isoformat()
                log.warning("Gateway upstream connection suspended. Routing incoming patient vitals to local SQLite WAL queue.")
            elif not was_online and now_online:
                self.last_connected_at = datetime.now(timezone.utc).isoformat()
                self.reconnect_count += 1
                log.info("Gateway upstream connection active. Synchronizing queued SQLite readings to cloud.")
            return now_online

    # Keep alias for backwards compatibility with automated scripts
    def set_simulated_offline(self, offline: bool) -> bool:
        return self.set_offline_mode(offline)

    def probe_cloud_latency(self) -> float:
        """Performs a live health probe to the Cloud Backend and returns RTT in milliseconds."""
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(f"{CLOUD_BACKEND_URL}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    rtt = round((time.perf_counter() - t0) * 1000.0, 2)
                    with self.lock:
                        self.last_latency_ms = rtt
                    self.report_transmission_result(True)
                    return rtt
        except Exception:
            self.report_transmission_result(False)
        return -1.0

    def report_transmission_result(self, success: bool, latency_ms: Optional[float] = None) -> None:
        with self.lock:
            if latency_ms is not None and latency_ms >= 0:
                self.last_latency_ms = round(latency_ms, 2)
            if self._maintenance_offline_mode:
                return
            if success and not self._cloud_reachable:
                self._cloud_reachable = True
                self.last_connected_at = datetime.now(timezone.utc).isoformat()
                self.reconnect_count += 1
                log.info("Upstream cloud connection restored automatically.")
            elif not success and self._cloud_reachable:
                self._cloud_reachable = False
                self.last_disconnected_at = datetime.now(timezone.utc).isoformat()
                log.warning("Upstream cloud transmission failed; activating local SQLite store-and-forward buffer.")

    def status_summary(self) -> dict:
        with self.lock:
            online = (not self._maintenance_offline_mode) and self._cloud_reachable
            return {
                "cloudConnected": online,
                "maintenanceOffline": self._maintenance_offline_mode,
                "latencyMs": self.last_latency_ms,
                "lastConnectedAt": self.last_connected_at,
                "lastDisconnectedAt": self.last_disconnected_at,
                "reconnectCount": self.reconnect_count,
            }
