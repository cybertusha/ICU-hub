# Hardware Connection & Sensor Integration Guide
## Real-Time IoT-Based ICU Patient Monitoring System

> **SAFETY WARNING:** Do not connect unisolated breadboard sensors to mains-powered equipment while attached to a human subject. In `HARDWARE` mode, power the setup from a medical-grade isolated USB power bank or use simulated signals until supervised by a biomedical lab instructor.

---

## 1. Supported Biomedical Sensors (`MODE 2: HARDWARE MODE`)

The `raspberry-pi-gateway/sensor_manager.py` module provides plug-and-play drivers for three standard biomedical prototype sensors:

| Vital Parameter | Recommended Sensor Module | Interface | Raspberry Pi GPIO Pins |
|---|---|---|---|
| **Heart Rate & SpO₂** | **MAX30102** Pulse Oximeter | I2C (`0x57`) | `VCC` → Pin 1 (`3.3V`), `GND` → Pin 6, `SDA` → Pin 3 (`GPIO2`), `SCL` → Pin 5 (`GPIO3`) |
| **Body Temperature** | **DS18B20** Waterproof Probe | 1-Wire | `VCC` → Pin 1 (`3.3V`), `GND` → Pin 9, `DQ` → Pin 7 (`GPIO4`, with `4.7kΩ` pull-up resistor to `3.3V`) |
| **Single-Lead ECG** | **AD8232** + **MCP3008** ADC | SPI0 (`CE0`) | `VDD/VREF` → `3.3V`, `AGND/DGND` → `GND`, `CLK` → Pin 23 (`GPIO11`), `DOUT` → Pin 21 (`GPIO9`), `DIN` → Pin 19 (`GPIO10`), `CS` → Pin 24 (`GPIO8`) |

---

## 2. Enabling Hardware Interfaces on Raspberry Pi OS

Run `sudo raspi-config` → **Interface Options** and enable:
1. **I2C** (`sudo modprobe i2c-dev`)
2. **SPI** (`sudo modprobe spi-bcm2835`)
3. **1-Wire** (add `dtoverlay=w1-gpio` to `/boot/firmware/config.txt` and reboot)

Verify attached sensors before starting Hardware Mode:
```bash
i2cdetect -y 1                 # Should show 0x57 for MAX30102
ls /sys/bus/w1/devices/28-*    # Should list DS18B20 serial directory
```

Then start the gateway in Hardware Mode:
```bash
cd raspberry-pi-gateway
python3 main.py --mode HARDWARE
```
