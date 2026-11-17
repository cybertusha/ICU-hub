# Setup & Deployment Guide
## Real-Time IoT-Based ICU Patient Monitoring System (`ICUGuardian`)

---

## 1. Quick Start (Live College Presentation Mode — Single Command)

You can launch the entire 4-tier ecosystem (Bedside ICU Monitor PC + Raspberry Pi Gateway + AWS/Local Cloud Backend + Doctor Web Dashboard) with a single script:

```bash
chmod +x start_demo.sh
./start_demo.sh
```

Once started, open the following URLs in your browser:
1. **Doctor Web Application (`ICUGuardian`):** [http://localhost:3000](http://localhost:3000)
   - **Quick Demo Logins:**
     - Doctor: `doctor` / `doctor123` (or click **Demo Doctor**)
     - Nurse: `nurse` / `nurse123` (or click **Demo Nurse**)
     - Admin: `admin` / `admin123` (or click **Demo Admin**)
2. **Bedside ICU Patient Monitor (PC Simulator):** [http://localhost:3001](http://localhost:3001)
3. **Raspberry Pi Gateway Status Endpoint:** [http://localhost:5050/gateway/status](http://localhost:5050/gateway/status)
4. **Cloud Backend API & WebSocket Health:** [http://localhost:8000/api/health](http://localhost:8000/api/health) (`ws://localhost:8000/ws`)

---

## 2. Running Multi-Device Setup (PC + Physical Raspberry Pi + AWS Cloud)

### Step A: Provision AWS Cloud Infrastructure
1. Configure AWS CLI credentials (`aws configure`) on your deployment machine.
2. Register the Raspberry Pi Thing and generate X.509 certificates:
   ```bash
   cd aws-cloud/iot-core
   chmod +x register_pi_thing.sh
   ./register_pi_thing.sh ICU-PI-001
   ```
3. Deploy the DynamoDB tables and Serverless Lambda functions:
   ```bash
   cd ../deployment
   chmod +x deploy_aws.sh
   ./deploy_aws.sh
   ```

### Step B: Start the Raspberry Pi IoT Gateway
On your Raspberry Pi (connected to the same LAN/Wi-Fi as the Bedside PC):
```bash
cd raspberry-pi-gateway
pip3 install -r requirements.txt
export DEVICE_ID="ICU-PI-001"
export OPERATING_MODE="SIMULATION"   # Or HARDWARE when sensors are attached
export CLOUD_BACKEND_URL="http://<CLOUD_OR_HOST_IP>:8000"
python3 main.py
```

### Step C: Start the Bedside ICU Patient Monitor on the PC
```bash
cd patient-monitor-pc
export GATEWAY_URL="http://<RASPBERRY_PI_IP>:5050/gateway/telemetry"
python3 server.py
```
Open `http://localhost:3001` to view the dark bedside ICU monitor with real-time sweeping ECG waveform and scenario buttons.

### Step D: Start the Doctor Web Application
```bash
cd doctor-dashboard
python3 server.py
```
Open `http://localhost:3000` on a second laptop, tablet, or projector display.
