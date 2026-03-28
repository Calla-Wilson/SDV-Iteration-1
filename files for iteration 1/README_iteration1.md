# SDV-Iteration-1: Software-Defined Vehicle Data Pipeline

## SOFE 3290U — Software Quality and Project Management | Group 21

A fully containerized Software-Defined Vehicle (SDV) data pipeline that simulates vehicle telemetry, processes it through an industry-standard SDV stack, and exposes it via a diagnostic API. The system demonstrates end-to-end data flow from a vehicle simulator through Eclipse Kuksa, Eclipse Zenoh, and Eclipse Ditto, with an Eclipse OpenSOVD-inspired diagnostic interface.

---

## System Architecture

```
Vehicle Simulator (send_obd_data_to_kuksa.py)
        │
        ▼
  Eclipse Kuksa (:55555)            — Vehicle Data Abstraction Layer
        │
        ▼
  kuksa_to_zenoh.py                 — Bridge + Overheat Fault Detection
        │
        ▼
  Eclipse Zenoh (:7447)             — Distributed Data Transport
        │
        ▼
  ditto-adapter.py                  — Safety Rules Engine + Zenoh-to-Ditto Bridge
        │
        ▼
  Eclipse Ditto (:8080)             — Digital Twin Backend (MongoDB storage)
        │
        ▼
  diagnostic-api.py (:20002)        — OpenSOVD Diagnostics Interface
```

---

## SDV Components

| Component | Role | Port |
|-----------|------|------|
| **Eclipse Kuksa** | Vehicle data abstraction layer. Receives and normalizes raw OBD signals into a structured vehicle model. Acts as the single source of truth for vehicle state. | 55555 |
| **Eclipse Zenoh** | Distributed data transport. Routes vehicle telemetry from Kuksa to Ditto, enabling simulation of real-world network conditions. | 7447 |
| **Eclipse Ditto** | Digital twin backend. Persists vehicle state over time, manages the digital twin for vehicle-21, applies safety rules and policies, and exposes REST APIs. | 8080 |
| **Eclipse OpenSOVD** (diagnostic-api) | Vehicle diagnostics interface. Queries Ditto for vehicle health, detects and reports faults, and provides diagnostic endpoints. | 20002 |

---

## Prerequisites

- **Docker Desktop** — [Download here](https://docs.docker.com/desktop/setup/install/windows-install/)
- **Git** — [Download here](https://gitforwindows.org/)

After installing Docker Desktop, restart your computer and ensure Docker Desktop is running (whale icon in system tray) before proceeding.

---

## Project Structure

```
SDV-Iteration-1/
├── docker-compose.yml              # Orchestrates all containers
├── Dockerfile.adapter              # Builds ditto-adapter container
├── Dockerfile.bridge               # Builds kuksa-to-zenoh bridge container
├── Dockerfile.diagnostic           # Builds OpenSOVD diagnostic API container
├── nginx.conf                      # Nginx reverse proxy config for Ditto
├── nginx.htpasswd                  # Ditto basic auth credentials (devops:foobar)
├── OBD.json                        # Kuksa vehicle signal definitions (VSS)
├── policy.json                     # Ditto access control policy
├── VSS_Ditto.json                  # Ditto digital twin model definition
├── kuksa_to_zenoh.py               # Bridge: reads Kuksa → publishes to Zenoh
├── ditto-adapter.py                # Bridge: subscribes Zenoh → updates Ditto
├── diagnostic-api.py               # OpenSOVD diagnostic REST API
├── send_obd_data_to_kuksa.py       # Vehicle simulator (36-second sequence)
├── retrieve_obd_data_from_kuksa.py # Utility: reads current Kuksa values
├── vehicle_data_source.py          # Standalone data source (JSON output)
└── README.md
```

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Calla-Wilson/SDV-Iteration-1.git
cd SDV-Iteration-1
```

### 2. Start the Pipeline

```bash
docker compose up -d
```

This pulls all required images and starts 12 containers (Kuksa, Zenoh, MongoDB, 5 Ditto microservices, Nginx, kuksa-to-zenoh bridge, ditto-adapter, and diagnostic-api). First run takes 5–10 minutes depending on internet speed.

### 3. Wait for Ditto to Initialize

Ditto's Java microservices take approximately 1–2 minutes to fully start. Check status:

```bash
docker compose ps
```

Verify Ditto is healthy:

```bash
curl -u devops:foobar http://localhost:8080/status/health
```

Expected response: `{"status":"UP"}`

### 4. Create the Ditto Policy and Thing

Before running the simulator for the first time, create the access policy and digital twin:

```bash
curl -X PUT -u devops:foobar http://localhost:8080/api/2/policies/org.ovin:my-policy \
  -H 'Content-Type: application/json' \
  -d '{"entries":{"DEFAULT":{"subjects":{"nginx:devops":{"type":"Ditto user authenticated via nginx"}},"resources":{"policy:/":{"grant":["READ","WRITE"],"revoke":[]},"thing:/":{"grant":["READ","WRITE"],"revoke":[]},"message:/":{"grant":["READ","WRITE"],"revoke":[]}}}}}'
```

```bash
curl -X PUT -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21 \
  -H 'Content-Type: application/json' \
  -d '{"policyId":"org.ovin:my-policy","features":{}}'
```

### 5. Run the Vehicle Simulator

```bash
docker compose run --rm simulator
```

This sends 36 seconds of simulated vehicle data through the full pipeline, covering 6 driving phases: Idle → Accelerating → Turning → Cruising → Overheat Fault → Safety Slowdown.

---

## Verifying the Pipeline

### Check Kuksa-to-Zenoh Bridge Logs

```bash
docker compose logs kuksa-to-zenoh | grep "Published"
```

### Check Ditto Adapter Logs

```bash
docker compose logs ditto-adapter | tail -20
```

### Query the Digital Twin (Ditto REST API)

```bash
# Full Thing state
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21 | python3 -m json.tool

# OBD telemetry
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21/features/OBD | python3 -m json.tool

# Safety constraints
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21/features/Safety | python3 -m json.tool

# Diagnostics
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21/features/Diagnostics | python3 -m json.tool
```

### Query via OpenSOVD Diagnostic API

```bash
# Vehicle discovery
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21 | python3 -m json.tool

# All OBD data
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/data/OBD | python3 -m json.tool

# Specific signal
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/data/OBD/VehicleSpeed | python3 -m json.tool

# System diagnostics
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/diagnostics | python3 -m json.tool

# Active faults
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/faults | python3 -m json.tool
```

---

## Functional Modification: Overheat Safety Constraint

The system implements an engine overheat detection and safety constraint mechanism that spans multiple components:

**Detection (kuksa_to_zenoh.py):** When `CoolantTemperature >= 110°C`, the bridge flags the telemetry payload with `fault_active: true` and `fault_code: "ENGINE_OVERHEAT"`.

**Safety Rules (ditto-adapter.py):** The adapter evaluates safety rules on each update:
- Sets `Safety/OverheatActive = true` and `Safety/SafetyConstraintActive = true`
- Logs the fault to `Diagnostics/FaultHistory`
- Sets `Diagnostics/SystemHealth = "CRITICAL"`
- Implements hysteresis: fault clears only when temperature drops below 105°C

**Diagnostics (diagnostic-api.py):** The OpenSOVD API exposes fault information via `/faults` and `/diagnostics` endpoints.

This can be observed during simulation phases 5–6 (t=25 to t=36), where engine temperature rises from 110°C to 120°C before the safety slowdown phase begins.

---

## Simulation Phases

| Phase | Time (s) | Speed (km/h) | Engine Temp (°C) | Description |
|-------|----------|---------------|-------------------|-------------|
| Idle | 0–5 | 0 | 80 | Vehicle stationary |
| Accelerating | 6–12 | 10→52 | 85→94 | Speed increases |
| Turning | 13–18 | 40 | 95 | Steering angle changes |
| Cruising | 19–24 | 55 | 100 | Steady state |
| Overheat Fault | 25–30 | 50 | 110→120 | Fault triggered at 110°C |
| Safety Slowdown | 31–36 | 50→20 | 118 | Speed reduced due to fault |

---

## Stopping the Pipeline

```bash
docker compose down
```

To also remove stored data (MongoDB volume):

```bash
docker compose down -v
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `docker: command not found` | Docker Desktop is not running. Open it and wait for "running" status. |
| Containers keep restarting | Check logs: `docker compose logs <service-name>` |
| `connection refused` on curl | Ditto takes 1–2 min to start. Wait and retry. |
| Port already in use | Stop conflicting service or change port in docker-compose.yml |
| Thing not found (404) | Run the policy and Thing creation commands from Step 4. |
| To fully reset | `docker compose down -v && docker compose build --no-cache && docker compose up -d` |

---

## Team Members

| Name | Student Number |
|------|----------------|
| Muhammad Areeb Khan | 100821104 |
| Ebubechukwu Agwagah | 100937022 |
| Calla Wilson | 100785022 |
| Shekina Hien | 100807845 |
| Nehal Rauf | 100825220 |
| Gabriel McLachlan | 100919944 |
