#!/usr/bin/env python3
"""
ICUGuardian — Doctor Web Application Server (`doctor-dashboard/server.py`)
Serves the Doctor Web Dashboard on http://localhost:3000.
"""

import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = int(os.environ.get("DASHBOARD_PORT", "3000"))
PUBLIC_DIR = Path(__file__).parent / "public"


class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print(f"[ICUGuardian — Doctor Dashboard] Running on http://localhost:{PORT}")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHTTPHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Doctor Dashboard...")
