# SDV Pipeline - Setup & Run Guide

## Prerequisites

1. **Install Docker Desktop**
   - Download from: https://docs.docker.com/desktop/setup/install/windows-install/
   - During installation, accept the WSL 2 option if prompted
   - **Restart your computer** after installation

2. **Start Docker Desktop**
   - Open Docker Desktop from the Start menu
   - Wait until the whale icon in the system tray says "Docker Desktop is running"
   - This must be running before any commands below will work

3. **Install Git** (if not already installed)
   - Download from: https://gitforwindows.org/

---

## Folder Structure

Before running, make sure the project folder contains all of these files:

```
SDV-Iteration-1/
├── docker-compose.yml          # Orchestrates all containers
├── Dockerfile.adapter          # Builds the Ditto adapter container
├── Dockerfile.bridge           # Builds the Kuksa-to-Zenoh bridge container
├── Dockerfile.diagnostic       # Builds the OpenSOVD diagnostic API container
├── OBD.json                    # Vehicle signal definitions for Kuksa
├── kuksa_to_zenoh.py           # Bridge: reads Kuksa, publishes to Zenoh
├── ditto-adapter.py            # Bridge: subscribes Zenoh, updates Ditto
├── diagnostic-api.py           # OpenSOVD API: queries Ditto for health/faults
├── send_obd_data_to_kuksa.py   # Simulator: sends 36s of vehicle data to Kuksa
├── retrieve_obd_data_from_kuksa.py
├── vehicle_data_source.py
├── policy.json                 # Ditto access control policy
└── VSS_Ditto.json              # Ditto digital twin model
```

**If any of these are missing, the build will fail.** Double check before proceeding.

---

## Step 1: Start the Pipeline

Open PowerShell (or VS Code terminal), navigate to the project folder:

```powershell
cd path\to\SDV-Iteration-1
```

Start all services:

```powershell
docker compose up -d
```

This downloads images and builds containers. **First run takes 5-10 minutes** depending on internet speed. Subsequent runs are much faster.

You should see something like:

```
[+] Running 7/7
 ✔ Network sdv-network        Created
 ✔ Container mongodb           Healthy
 ✔ Container kuksa             Started
 ✔ Container zenoh             Started
 ✔ Container ditto             Healthy
 ✔ Container kuksa-to-zenoh    Started
 ✔ Container ditto-adapter     Started
 ✔ Container diagnostic-api    Started
```

---

## Step 2: Wait for Ditto to Be Ready

Ditto takes about 30-60 seconds to fully start. Check if it's healthy:

```powershell
docker compose ps
```

All services should show "running" or "healthy". If ditto shows "starting", wait and check again.

You can also test Ditto directly:

```powershell
curl http://localhost:8080/status/health
```

If you get a JSON response, Ditto is ready.

---

## Step 3: Run the Vehicle Simulator

This sends 36 seconds of simulated vehicle data through the pipeline:

```powershell
docker compose run --rm simulator
```

You'll see output like:

```
Time = 0
Vehicle Speed = 0
Engine Temperature = 80
Steering Angle = 0
Battery Level = 95
-----------------------------
Time = 1
...
```

The simulation covers 6 phases: Idle → Accelerating → Turning → Cruising → Overheat Fault → Safety Slowdown.

---

## Step 4: Verify Data Flow

### Check Kuksa → Zenoh bridge logs:

```powershell
docker compose logs kuksa-to-zenoh
```

### Check Ditto adapter logs (should show safety rule evaluations):

```powershell
docker compose logs ditto-adapter
```

### Query the Ditto digital twin directly:

```powershell
curl http://localhost:8080/api/2/things/vehicle-21
curl http://localhost:8080/api/2/things/vehicle-21/features/OBD
curl http://localhost:8080/api/2/things/vehicle-21/features/Safety
curl http://localhost:8080/api/2/things/vehicle-21/features/Diagnostics
```

### Query via OpenSOVD diagnostic API:

```powershell
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/data/OBD
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/data/OBD/VehicleSpeed
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/diagnostics
curl http://localhost:20002/sovd/v1/vehicles/vehicle-21/faults
```

---

## Step 5: Stop Everything

```powershell
docker compose down
```

To also remove stored data (MongoDB volume):

```powershell
docker compose down -v
```

---

## Pipeline Overview

```
Vehicle Simulator (send_obd_data_to_kuksa.py)
        │
        ▼
  Eclipse Kuksa (:55555)         ← Vehicle Data Abstraction Layer
        │
        ▼
  kuksa_to_zenoh.py              ← Bridge + Overheat Fault Detection
        │
        ▼
  Eclipse Zenoh (:7447)          ← Distributed Data Transport
        │
        ▼
  ditto-adapter.py               ← Safety Rules Engine + Zenoh-to-Ditto Bridge
        │
        ▼
  Eclipse Ditto (:8080)          ← Digital Twin Backend (MongoDB storage)
        │
        ▼
  diagnostic-api.py (:20002)     ← OpenSOVD Diagnostics Interface
```

---

## Functional Modification

**Overheat Safety Constraint:** When CoolantTemperature >= 110°C:
- kuksa_to_zenoh.py flags `fault_active: true` with code `ENGINE_OVERHEAT`
- ditto-adapter.py sets Safety feature: `OverheatActive=true`, `SafetyConstraintActive=true`
- Fault is logged to Diagnostics feature `FaultHistory`
- Fault clears when temperature drops below 105°C (hysteresis)

This can be observed during simulation phases 5 and 6 (t=25 to t=36).

---

## Troubleshooting

**"docker: command not found"**
→ Docker Desktop is not running or not installed. Open Docker Desktop first.

**Containers keep restarting**
→ Check logs: `docker compose logs <service-name>` (e.g., `docker compose logs ditto-adapter`)

**curl commands return "connection refused"**
→ Service isn't ready yet. Wait 30-60 seconds for Ditto, then try again.

**Port already in use**
→ Something else is using that port. Stop it or change the port in docker-compose.yml.

**First-time build is slow**
→ Normal. Docker is downloading base images. Subsequent runs use cached layers.

**To fully reset and start fresh:**
```powershell
docker compose down -v
docker compose build --no-cache
docker compose up -d
```


dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart