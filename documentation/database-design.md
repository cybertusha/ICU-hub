# Database Design Specification (Amazon DynamoDB)
## Real-Time IoT-Based ICU Patient Monitoring System

---

## 1. Entity-Relationship Overview

```mermaid
erDiagram
    PATIENTS ||--o{ VITAL_READINGS : "generates (1:N)"
    PATIENTS ||--o{ ALERTS : "triggers (1:N)"
    DEVICES ||--|| PATIENTS : "monitors (1:1)"
    THRESHOLD_CONFIGS ||--o{ ALERTS : "evaluates"
    USERS ||--o{ ALERTS : "acknowledges / resolves"

    PATIENTS {
        string patientId PK
        string patientName
        int age
        string gender
        string bedNumber
        string monitoringDeviceId
        string monitoringStatus
        string condition
        string attendingPhysician
        string primaryNurse
        list allergies
        list currentMedications
        string createdAt
        string updatedAt
    }

    VITAL_READINGS {
        string patientId PK
        string timestamp SK
        string messageId
        string deviceId
        number heartRate
        number spo2
        number temperature
        number respiratoryRate
        map bloodPressure
        list ecg
        string operatingMode
        number ttl
    }

    ALERTS {
        string patientId PK
        string createdAt SK
        string alertId
        string parameter
        string category
        int priority
        number detectedValue
        string threshold
        string severity
        string description
        boolean acknowledged
        string acknowledgedBy
        string acknowledgedAt
        boolean resolved
        string resolvedBy
        string resolvedAt
        string recoveredAt
    }

    DEVICES {
        string deviceId PK
        string deviceName
        string deviceType
        string location
        string ipAddress
        string deviceStatus
        string uptime
        string lastSeen
        string firmwareVersion
        string operatingMode
        string assignedPatientId
    }

    THRESHOLD_CONFIGS {
        string configurationId PK
        map heartRate
        map spo2
        map temperature
        map respiratoryRate
        map bloodPressure
        int cooldownSeconds
        string updatedAt
    }

    USERS {
        string userId PK
        string username
        string fullName
        string role
        string department
        string email
        string phone
        boolean active
        string lastLogin
    }
```

---

## 2. Amazon DynamoDB Table Specifications

### Table 1: `ICU_Patients`
- **Partition Key (PK):** `patientId` (`S`) — e.g., `PATIENT-001`
- **Global Secondary Index (`BedNumberIndex`):** PK `bedNumber` (`S`)
- **Billing Mode:** `PAY_PER_REQUEST` (On-Demand)
- **Seed Records (Matching Figma Design):**
  1. `PATIENT-001` — **Emily Johnson** (45y, F, Bed `ICU-01`, Device `ICU-PI-001`, Post-operative monitoring, Dr. Sarah Smith)
  2. `PATIENT-002` — **Michael Chen** (62y, M, Bed `ICU-02`, Device `ICU-PI-002`, Acute coronary syndrome, Dr. Sarah Smith)
  3. `PATIENT-003` — **Sarah Davis** (58y, F, Bed `ICU-03`, Device `ICU-PI-003`, Severe pneumonia / respiratory distress, Dr. James Wilson)
  4. `PATIENT-004` — **James Thompson** (71y, M, Bed `ICU-04`, Device `ICU-PI-004`, Post-cardiac catheterization, Dr. Sarah Smith)
  5. `PATIENT-005` — **Maria Rodriguez** (39y, F, Bed `ICU-05`, Device `ICU-PI-005`, Sepsis recovery monitoring, Dr. James Wilson)
  6. `PATIENT-006` — **Robert Kim** (54y, M, Bed `ICU-06`, Device `ICU-PI-006`, Neurological observation, Dr. Sarah Smith)

### Table 2: `ICU_VitalReadings`
- **Partition Key (PK):** `patientId` (`S`)
- **Sort Key (SK):** `timestamp` (`S`) — ISO-8601 UTC string (`YYYY-MM-DDTHH:mm:ss.sssZ`)
- **Global Secondary Index (`MessageIdIndex`):** PK `messageId` (`S`) — used for idempotent deduplication when Raspberry Pi flushes offline queues.
- **TTL Attribute:** `ttl` (`N`) — Configurable retention (default 30 days).

### Table 3: `ICU_Alerts`
- **Partition Key (PK):** `patientId` (`S`)
- **Sort Key (SK):** `createdAt` (`S`)
- **Global Secondary Index 1 (`AlertIdIndex`):** PK `alertId` (`S`) — for direct `ACK` and `RESOLVE` updates by `alertId`.
- **Global Secondary Index 2 (`SeverityTimestampIndex`):** PK `severity` (`S`), SK `createdAt` (`S`) — for filtering alerts by severity across all ICU beds.

### Table 4: `ICU_Devices`
- **Partition Key (PK):** `deviceId` (`S`) — e.g., `ICU-PI-001` through `ICU-PI-006`, plus `ICU-HUB-MAIN`.
- **Attributes:** `deviceName`, `deviceType`, `location`, `ipAddress`, `deviceStatus`, `uptime`, `lastSeen`, `firmwareVersion`, `operatingMode`, `assignedPatientId`, `offlineQueueSize`.

### Table 5: `ICU_ThresholdConfigurations`
- **Partition Key (PK):** `configurationId` (`S`) — `DEFAULT_DEMO_THRESHOLDS` (or per-patient `PATIENT-001`).
- **Stores:** Configurable warning and critical bounds for Heart Rate, SpO2, Temperature, Respiratory Rate, Blood Pressure, and Alert Cooldown seconds.

### Table 6: `ICU_Users`
- **Partition Key (PK):** `userId` (`S`)
- **Global Secondary Index (`UsernameIndex`):** PK `username` (`S`)
- **Seed Users:**
  - `USR-001`: **Dr. Sarah Smith** (`doctor` / `Doctor`, Cardiology, `sarah.smith@hospital.com`)
  - `USR-002`: **Nurse Michael Jones** (`nurse` / `Nurse`, ICU, `michael.jones@hospital.com`)
  - `USR-003`: **Admin Lisa Wilson** (`admin` / `Admin`, IT & Biomedical Eng, `lisa.wilson@hospital.com`)
  - `USR-004`: **Dr. James Wilson** (`doctor2` / `Doctor`, Pulmonary ICU, `james.wilson@hospital.com`)

### Table 7: `ICU_WebSocketConnections`
- **Partition Key (PK):** `connectionId` (`S`)
- **TTL Attribute:** `ttl` (`N`)
- **Purpose:** Tracks connected Doctor Dashboard WebSocket clients for AWS API Gateway WebSocket fan-out broadcasts.
