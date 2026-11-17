# Complete Beginner-to-End Physical Setup Guide for College Project Presentation
## Physical Flow: College ICU Monitor / PC → LAN Ethernet Cable → Raspberry Pi 5 (with Local Pi Dashboard) → AWS Cloud → Doctor Dashboard

---

## Overview of What You Will Have on Your Presentation Table

On presentation day, your physical table will have **three visible screens** connected in a real hardware chain:

1. **Device 1 — College ICU Monitor / PC (`IP: 192.168.50.10`):**
   - Runs the ICU Patient Monitor program (`patient-monitor-pc/server.py` on `http://localhost:3001`) OR your college lab's ICU patient monitor software.
   - Connected via a **physical RJ45 LAN (Ethernet) cable** directly into the **Raspberry Pi 5's Ethernet port (`eth0`)**.
2. **Device 2 — Raspberry Pi 5 (`eth0 IP: 192.168.50.1`, plus Wi-Fi/Hotspot `wlan0` for Internet):**
   - Receives the exact patient readings coming through the LAN cable from the College PC (it does **not** generate random numbers of its own).
   - Displays a **Local Raspberry Pi 5 Gateway Dashboard** (`http://localhost:5050`) on a monitor/screen attached to the Raspberry Pi 5 so the examiners can see the exact packet arriving on the Pi in real time.
   - Validates the data and uploads it over **Wi-Fi / Mobile Hotspot (`wlan0`)** to **AWS IoT Core & AWS Cloud**.
3. **Device 3 — Doctor Dashboard Laptop / Tablet / Phone:**
   - Connected to the internet (e.g., mobile hotspot or college Wi-Fi—**not** wired to the ICU monitor).
   - Opens the **Doctor Dashboard (`ICUGuardian`)** and automatically displays the exact same live Heart Rate, SpO₂, Blood Pressure, Temperature, Respiratory Rate, ECG waveform, and Alerts arriving through AWS Cloud.

---

## STEP 1: Required Hardware, Cables & Ports Checklist

Before starting, gather these exact items:

| # | Item | Quantity | Exact Port / Specification |
|---|---|---|---|
| 1 | **College ICU Monitor / PC** | 1 | Must have an **RJ45 Ethernet (LAN) port** (or a USB-to-Ethernet adapter if it is a thin laptop) |
| 2 | **Raspberry Pi 5** (with Raspberry Pi OS installed on microSD card) | 1 | Uses its built-in **Gigabit Ethernet port (`eth0`)** AND built-in **Wi-Fi (`wlan0`)** |
| 3 | **Raspberry Pi 5 Power Supply** | 1 | Official **27W (5V / 5A) USB-C Power Supply** plugged into the Pi 5's `POWER IN` USB-C port |
| 4 | **CAT6 or CAT5e RJ45 Ethernet Patch Cable** | 1 | Standard straight-through LAN cable (1.5m – 3m). *(Raspberry Pi 5 has Auto-MDIX, so a normal LAN cable works for direct PC-to-Pi connection)* |
| 5 | **Monitor + Micro-HDMI to HDMI Cable + USB Keyboard/Mouse** (for Raspberry Pi 5) | 1 set | Plug the Micro-HDMI cable into the **`HDMI0` port** (the micro-HDMI port closest to the USB-C power port on Raspberry Pi 5) |
| 6 | **Smartphone Mobile Hotspot** (or College Wi-Fi) | 1 | Provides internet to the Raspberry Pi 5 (`wlan0`) and the Doctor Dashboard laptop/phone |
| 7 | **USB Pen Drive** (or GitHub) | 1 | To copy this `ICU` project folder onto the College PC and the Raspberry Pi 5 |

---

## STEP 2: Physical Cable Connections (How to Plug Everything In)

1. **Power on the Raspberry Pi 5:**
   - Insert your microSD card into the Raspberry Pi 5.
   - Connect the **Micro-HDMI cable** from port `HDMI0` on the Raspberry Pi 5 to a display monitor.
   - Connect a USB mouse and keyboard to the Raspberry Pi 5 USB ports.
   - Plug the **USB-C power supply** into the Raspberry Pi 5 and wait for the Raspberry Pi OS desktop to appear.
2. **Connect the LAN (Ethernet) Cable:**
   - Plug **End A** of the RJ45 Ethernet cable into the **Ethernet (`eth0`) port** of the **Raspberry Pi 5**.
   - Plug **End B** of the RJ45 Ethernet cable directly into the **Ethernet (LAN) port** of the **College ICU Monitor PC**.
   - Confirm that the green and amber link LEDs on the Raspberry Pi 5's Ethernet jack light up.
3. **Connect Raspberry Pi 5 to Internet via Wi-Fi (`wlan0`):**
   - Click the Wi-Fi icon in the top-right corner of the Raspberry Pi 5 desktop and connect to your **Phone's Mobile Hotspot** (recommended for college presentations because college firewalls often block MQTT port `8883`).

---

## STEP 3: Configure IP Addresses on the LAN Cable (PC ↔ Raspberry Pi 5)

Because the College PC and the Raspberry Pi 5 are connected directly with one Ethernet cable (with no router in between), you must give both ends of the cable a **Static IP Address** on the same subnet (`192.168.50.x`):
- **Raspberry Pi 5 Ethernet (`eth0`) IP:** `192.168.50.1`
- **College ICU Monitor PC Ethernet IP:** `192.168.50.10`

### 3A. Set Static IP `192.168.50.1` on the Raspberry Pi 5
Open the **Terminal** on the Raspberry Pi 5 and run these exact commands:

```bash
# 1. Create a permanent static IP profile for the Ethernet port (eth0)
#    Note: ipv4.never-default yes is CRITICAL so the Pi still uses Wi-Fi (wlan0) for AWS internet!
sudo nmcli connection add type ethernet con-name icu-lan ifname eth0 \
  ipv4.method manual \
  ipv4.addresses 192.168.50.1/24 \
  ipv4.never-default yes \
  ipv6.method ignore \
  connection.autoconnect yes

# 2. Activate the Ethernet connection
sudo nmcli connection up icu-lan

# 3. Verify that eth0 has IP 192.168.50.1
ip addr show eth0
```

### 3B. Set Static IP `192.168.50.10` on the College ICU Monitor PC

#### If the College PC runs **Windows 10 / Windows 11**:
1. Press `Win + R`, type `ncpa.cpl`, and press **Enter** (opens *Network Connections*).
2. Right-click **Ethernet** → click **Properties**.
3. Double-click **Internet Protocol Version 4 (TCP/IPv4)**.
4. Select **Use the following IP address** and enter:
   - **IP address:** `192.168.50.10`
   - **Subnet mask:** `255.255.255.0`
   - **Default gateway:** *(Leave blank!)*
5. Click **OK** → **OK**.

#### If the College PC runs **Ubuntu / Linux**:
Open a terminal on the College PC and run:
```bash
# Find the Ethernet interface name (usually eth0 or enp3s0)
ip link show

# Assign static IP 192.168.50.10/24 (replace enp3s0 with your Ethernet interface name)
sudo nmcli connection add type ethernet con-name pc-to-pi ifname enp3s0 \
  ipv4.method manual ipv4.addresses 192.168.50.10/24 ipv4.never-default yes
sudo nmcli connection up pc-to-pi
```

### 3C. Test the Physical LAN Cable Connection
On the **Raspberry Pi 5 Terminal**, ping the College PC:
```bash
ping -c 4 192.168.50.10
```
And on the **College PC Terminal / Command Prompt**, ping the Raspberry Pi 5:
```bash
ping 192.168.50.1
```
If both pings reply (`time<1ms`), your physical Ethernet link is working!

---

## STEP 4: Create and Configure AWS Cloud from Scratch (Beginner Step-by-Step)

Even if you have never used AWS before, follow these exact clicks in your web browser:

### 4.1 Create an AWS Account & Sign In
1. Go to [https://aws.amazon.com](https://aws.amazon.com) and sign in to the **AWS Management Console**.
2. In the top-right corner of the navigation bar, select the region **`US East (N. Virginia) us-east-1`** (keep this same region for every step).

### 4.2 Configure AWS IoT Core & Download Certificates for Raspberry Pi 5
AWS IoT Core is the secure MQTT broker that receives live patient data from your Raspberry Pi 5.

1. In the top AWS search bar, type **`IoT Core`** and open **AWS IoT**.
2. In the left sidebar, click **All devices** → **Things** → click the orange **Create things** button.
3. Select **Create single thing** → click **Next**.
4. Under **Thing name**, type:
   ```text
   ICU-PI-001
   ```
   Click **Next**.
5. Under **Device certificate**, select **Auto-generate a new certificate (recommended)** → click **Next**.
6. Under **Attach policies to certificate**, click **Create policy** (opens a new tab):
   - **Policy name:** `ICU_Gateway_Policy`
   - Switch the policy editor to **JSON** view and paste:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": ["iot:Connect", "iot:Publish", "iot:Subscribe", "iot:Receive"],
           "Resource": ["*"]
         }
       ]
     }
     ```
   - Click **Create**.
7. Go back to the **Create thing** browser tab, check the box next to `ICU_Gateway_Policy`, and click **Create thing**.
8. **IMPORTANT — Download the 3 Certificate Files** from the popup window and save them into your project's `raspberry-pi-gateway/certs/` folder with these exact filenames:
   - **Device certificate** → rename to **`device.pem.crt`**
   - **Private key file** → rename to **`private.pem.key`**
   - **Amazon Root CA 1** → rename to **`AmazonRootCA1.pem`**
   Click **Done**.
9. **Copy your AWS IoT Endpoint:**
   - In the AWS IoT Core left sidebar, scroll down and click **Settings**.
   - Under **Device data endpoint**, copy the address (it looks like `a1b2c3d4e5f6g7-ats.iot.us-east-1.amazonaws.com`). You will paste this into your Raspberry Pi environment variable `AWS_IOT_ENDPOINT`.

### 4.3 Create the Cloud Backend Server on AWS (or Run the Included Cloud Bridge)
You have **two ways** to run the AWS Cloud Backend (`cloud_backend_server.py`) so that both your Raspberry Pi 5 and Doctor Dashboard communicate through the cloud:

#### Option A (Easiest & Most Reliable for Live College Presentations — AWS EC2 Cloud Instance):
1. In AWS Console, search for **`EC2`** → click **Launch instance**.
2. Name: `ICU-Cloud-Backend`, OS: **Ubuntu 22.04 LTS**, Instance type: **`t2.micro` (Free Tier)**.
3. Create/select a key pair (`.pem`) and under **Network settings**, check:
   - Allow SSH traffic (`Port 22`)
   - Allow Custom TCP **`Port 8000`** (for Cloud REST & WebSocket API) and **`Port 3000`** (for Doctor Dashboard) from `Anywhere (0.0.0.0/0)`.
4. Launch the instance, copy its **Public IPv4 Address** (e.g. `54.210.XX.XX`), SSH into it, copy the `ICU` folder, and run:
   ```bash
   sudo apt update && sudo apt install -y python3-uvicorn python3-wsproto
   python3 aws-cloud/cloud_backend_server.py &
   python3 doctor-dashboard/server.py &
   ```
5. In **AWS IoT Core → Message routing → Rules → Create rule**:
   - **Rule name:** `ICU_ForwardToCloudBackend`
   - **SQL statement:** `SELECT * FROM 'icu/devices/+/vitals'`
   - **Action:** Choose **HTTP** → enter `http://<YOUR_EC2_PUBLIC_IP>:8000/api/iot/ingest-vitals` (or let `mqtt_client.py` on the Raspberry Pi post simultaneously to AWS IoT Core MQTT port `8883` and `CLOUD_BACKEND_URL`).

#### Option B (Automated AWS Serverless DynamoDB + Lambda Deployment):
If you have AWS CLI configured on your laptop (`aws configure`), run our automated provisioner from the project folder:
```bash
cd aws-cloud/iot-core
./register_pi_thing.sh ICU-PI-001
cd ../deployment
./deploy_aws.sh
```

---

## STEP 5: Communication Protocol & How Data Travels Across Every Hop

Here is how the exact same patient reading travels from the College ICU Monitor PC to the Raspberry Pi 5, onto the Local Pi Dashboard, up to AWS Cloud, and onto the Doctor Dashboard without the Raspberry Pi ever inventing fake random numbers:

1. **Hop 1 (College ICU Monitor PC → Ethernet Cable → Raspberry Pi 5):**
   - **Protocol:** HTTP POST JSON (`http://192.168.50.1:5050/gateway/telemetry`) **OR** HL7 v2.6 MLLP over TCP (`192.168.50.1:2575`).
   - The College PC reads/generates the dummy patient vitals displayed on its screen and transmits each reading over the physical Ethernet cable to `192.168.50.1`.
2. **Hop 2 (Inside the Raspberry Pi 5):**
   - `simulator_receiver.py` (or `icu_monitor_lan_driver.py`) receives the packet from `eth0`.
   - `data_processor.py` validates that Heart Rate, SpO₂, Blood Pressure, Temperature, and Respiratory Rate are within valid numeric ranges and attaches a unique `messageId` and UTC timestamp.
   - `GATEWAY_SERVICE` stores this exact validated packet in `self.latest_reading` and immediately serves it on the **Local Raspberry Pi 5 Dashboard (`http://localhost:5050/`)**.
3. **Hop 3 (Raspberry Pi 5 → Wi-Fi `wlan0` → AWS Cloud):**
   - `mqtt_client.py` publishes the exact same JSON packet over **MQTT over TLS v1.2 (Port 8883)** using `certs/device.pem.crt` and `certs/private.pem.key` to topic `icu/devices/ICU-PI-001/vitals`, and delivers it to `CLOUD_BACKEND_URL/api/iot/ingest-vitals`.
   - If the internet drops, `offline_queue.py` saves the packet into `offline_queue.db` (SQLite) on the Raspberry Pi 5 and automatically uploads it when internet returns.
4. **Hop 4 (AWS Cloud → Doctor Dashboard):**
   - The Cloud Backend stores the reading, evaluates alert thresholds (`CRITICAL` / `WARNING` / `NORMAL`), and immediately pushes a `VITAL_UPDATE` (and `ALERT_NEW` if abnormal) over **WebSocket (`/ws`)** to the Doctor Dashboard browser.

---

## STEP 6: Exact Commands to Run on Each Machine During Your Presentation

### Machine 1: On the Raspberry Pi 5
Copy the `ICU` project folder to `/home/pi/ICU` on the Raspberry Pi 5, open a terminal, and run:

```bash
cd /home/pi/ICU/raspberry-pi-gateway

# Set your AWS IoT Endpoint and Cloud Backend URL (use your EC2 Public IP or Laptop Hotspot IP)
export DEVICE_ID="ICU-PI-001"
export OPERATING_MODE="BEDSIDE_MONITOR"
export AWS_IOT_ENDPOINT="<YOUR_ENDPOINT>-ats.iot.us-east-1.amazonaws.com"
export CLOUD_BACKEND_URL="http://<CLOUD_OR_DOCTOR_LAPTOP_IP>:8000"

# Start the Raspberry Pi 5 Gateway
python3 main.py
```

Now open the **Chromium browser on the Raspberry Pi 5** and go to:
```text
http://localhost:5050
```
You will see the **Raspberry Pi 5 Local Bedside IoT Gateway Dashboard** on the Pi's screen!

---

### Machine 2: On the College ICU Monitor PC (`192.168.50.10`)
Open a terminal (or Command Prompt) on the College PC connected via the Ethernet cable and point `GATEWAY_URL` to the Raspberry Pi 5's Ethernet IP (`192.168.50.1`):

```bash
cd ICU/patient-monitor-pc

# Point the ICU Monitor PC directly to the Raspberry Pi 5 over the Ethernet cable!
export GATEWAY_URL="http://192.168.50.1:5050/gateway/telemetry"

python3 server.py
```
*(If using Windows PowerShell on the College PC, run `$env:GATEWAY_URL="http://192.168.50.1:5050/gateway/telemetry"; python server.py`).*

Now open the browser on the **College PC** to:
```text
http://localhost:3001
```
You will see the dark **Bedside ICU Patient Monitor** displaying the patient's live ECG waveform, SpO₂ wave, Heart Rate, SpO₂, Blood Pressure, Temperature, and Respiratory Rate—and every second it sends that exact reading over the Ethernet cable to `192.168.50.1:5050`!

---

### Machine 3: On the Cloud / Doctor Dashboard Laptop or Mobile Phone
If you are running the Cloud Backend + Doctor Dashboard on your AWS EC2 instance (or on a separate laptop connected to the Wi-Fi hotspot):

```bash
cd ICU
python3 aws-cloud/cloud_backend_server.py &
python3 doctor-dashboard/server.py &
```

Open the **Doctor Dashboard (`ICUGuardian`)** in the browser at:
```text
http://<CLOUD_OR_LAPTOP_IP>:3000
```
Sign in with:
- **Username:** `sarah.smith`
- **Password:** `doctor123`

---

## STEP 7: Step-by-Step Verification & Troubleshooting Guide

### How to Verify the Complete Chain Before the Examiners Arrive

1. **Check the Numbers Match Across All 3 Screens:**
   - Look at **Emily Johnson (`ICU-01`)** on the **College ICU Monitor PC (`http://localhost:3001`)**.
   - Look at the **Local Raspberry Pi 5 Dashboard (`http://localhost:5050`)** — verify that the Heart Rate, SpO₂, BP, Temp, RR, and `messageId` match the PC screen.
   - Look at the **Doctor Dashboard (`http://...:3000`)** — verify that Emily Johnson's row and individual patient chart show the exact same numbers!
2. **Test Live Abnormality & Alert Generation:**
   - On the **College ICU Monitor PC (`:3001`)**, click the **`Acute Hypoxemia`** (Low SpO₂) button.
   - Watch SpO₂ drop to ~86% on the College PC → appear immediately on the **Local Raspberry Pi 5 Dashboard (`:5050`)** → travel to AWS Cloud → trigger the **Red Critical Alert & Audio Alarm** on the **Doctor Dashboard (`:3000`)**!
3. **Test AWS IoT Core MQTT Reception in the AWS Console:**
   - Open **AWS Console → IoT Core → MQTT test client**.
   - Under **Subscribe to a topic**, enter:
     ```text
     icu/devices/#
     ```
   - Click **Subscribe**. You will see the live JSON messages arriving from `ICU-PI-001` every second inside the AWS Console!

### Quick Troubleshooting Table

| Problem | Cause | Exact Fix |
|---|---|---|
| College PC shows `Gateway: STANDALONE (Gateway Unreachable)` | Ethernet static IP not active or Windows Firewall blocking port `5050` | Run `ping 192.168.50.1` from the PC. On the Raspberry Pi 5, run `sudo ufw allow in on eth0 to any port 5050 proto tcp`. |
| Raspberry Pi 5 has no internet after plugging in the LAN cable | `eth0` took priority as the default gateway over `wlan0` | Run `sudo nmcli connection modify icu-lan ipv4.never-default yes && sudo nmcli connection up icu-lan` on the Raspberry Pi 5. |
| AWS IoT MQTT TLS fails to connect on college Wi-Fi | College campus Wi-Fi blocks outbound port `8883` | Connect the Raspberry Pi 5's Wi-Fi (`wlan0`) to your **smartphone's 4G/5G mobile hotspot**. |
| Doctor Dashboard does not play audio alarm on first alert | Browser autoplay policy requires one click on the page before playing Web Audio | Click anywhere on the Doctor Dashboard (e.g., sign in or click **Test Acoustic Alarm Tone** in Settings → Notifications). |
