# SDV-Iteration-2: System Extension, Validation, and Evaluation

## SOFE 3290U — Software Quality and Project Management | Group 21

Iteration 2 extends the baseline SDV pipeline from Iteration 1 by introducing system modifications, validating correct behavior, and measuring non-functional performance metrics.

---

## System Architecture

```
Vehicle Simulator (send_obd_data_to_kuksa.py)
        │
        ▼
  Eclipse Kuksa (:55555)            — Vehicle Data Abstraction Layer
        │
        ▼
  kuksa_to_zenoh.py                 — Bridge + Overheat Detection + Delay Injection
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

## What Changed in Iteration 2

### Zenoh Network Delay Injection

Configurable network delay was added to `kuksa_to_zenoh.py` to simulate real-world latency in vehicle-to-cloud communication. The delay is controlled via the `ZENOH_DELAY_MS` environment variable in `docker-compose.yml`.

**Files modified:**
- `kuksa_to_zenoh.py` — added `import os`, `ZENOH_DELAY_MS` config variable, and `asyncio.sleep()` before Zenoh publish
- `docker-compose.yml` — added `ZENOH_DELAY_MS=0` to the `kuksa-to-zenoh` service environment

---

## Setup and Run

### 1. Start the Pipeline

```bash
docker compose up -d
```

Wait 1–2 minutes for Ditto to initialize, then verify:

```bash
docker compose ps
curl -u devops:foobar http://localhost:8080/status/health
```

### 2. Create Ditto Policy and Thing (first run only)

```bash
curl -X PUT -u devops:foobar http://localhost:8080/api/2/policies/org.ovin:my-policy \
  -H 'Content-Type: application/json' \
  -d '{"entries":{"DEFAULT":{"subjects":{"nginx:devops":{"type":"Ditto user authenticated via nginx"}},"resources":{"policy:/":{"grant":["READ","WRITE"],"revoke":[]},"thing:/":{"grant":["READ","WRITE"],"revoke":[]},"message:/":{"grant":["READ","WRITE"],"revoke":[]}}}}}'

curl -X PUT -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21 \
  -H 'Content-Type: application/json' \
  -d '{"policyId":"org.ovin:my-policy","features":{}}'
```

### 3. Run the Simulator

```bash
docker compose run --rm simulator
```

### 4. Verify Data Flow

```bash
docker compose logs kuksa-to-zenoh | tail -20
docker compose logs ditto-adapter | tail -20
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21/features/OBD | python3 -m json.tool
```

---

## Running the Delay Experiment

### Baseline Run (no delay)

Ensure `ZENOH_DELAY_MS=0` in `docker-compose.yml`, then:

```bash
docker compose up -d --force-recreate kuksa-to-zenoh
docker compose run --rm simulator
docker compose logs kuksa-to-zenoh | tail -20
```

### Delayed Run (200ms)

Change `ZENOH_DELAY_MS=0` to `ZENOH_DELAY_MS=200` in `docker-compose.yml`, then:

```bash
docker compose up -d --force-recreate kuksa-to-zenoh
docker compose run --rm simulator
docker compose logs kuksa-to-zenoh | tail -20
```

The logs should show `delay=200ms` on each publish line. Verify the digital twin still updated:

```bash
curl -u devops:foobar http://localhost:8080/api/2/things/org.ovin:vehicle-21/features/OBD | python3 -m json.tool
```

---

## Stopping the Pipeline

```bash
docker compose down
docker compose down -v    # also removes MongoDB data
```

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