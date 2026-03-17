# Ditto Implementation

## Overview

Eclipse Ditto digital twin backend that stores vehicle state persistently and provides REST APIs for querying data. Ditto maintains a virtual representation of vehicle-21 with three features: OBD telemetry, Safety constraints, and Diagnostics.

## Architecture

Zenoh topic (vehicle/vehicle-21/telemetry) -> ditto-adapter.py -> Ditto API (port 8080) -> MongoDB

The adapter listens to Zenoh, translates messages to Ditto REST format, evaluates safety rules, and sends HTTP PUT requests to update the Thing.

## Thing Structure

Thing ID: vehicle-21

Features:
1. OBD: VehicleSpeed, EngineSpeed, ThrottlePosition, CoolantTemperature
2. Safety: OverheatActive, FaultCode, SafetyConstraintActive, LastFaultTime
3. Diagnostics: SystemHealth, DataUpdateCount, FaultHistory, LastDataUpdateTime

## Components

ditto-adapter.py: Bridges Zenoh to Ditto. Listens to vehicle/vehicle-21/telemetry, evaluates safety rules (overheat >= 110C), sends HTTP PUT requests to Ditto API.

VSS_Ditto.json: Digital twin model definition with all features and properties.

docker-compose.yml: Orchestrates Ditto (port 8080), MongoDB (port 27017), and adapter on sdv-network.

Dockerfile.adapter: Containerizes the Python adapter.

requirements-adapter.txt: Dependencies (zenoh, requests).

policy.json: Ditto access control.

## Setup

```bash
docker-compose up -d
```

Starts Ditto and MongoDB. Adapter connects automatically to http://ditto:8080.

## Verify Installation

```bash
curl http://localhost:8080/api/2/things
```

Returns empty array initially. Thing is created on first adapter update.

## Query the Digital Twin

```bash
curl http://localhost:8080/api/2/things/vehicle-21
curl http://localhost:8080/api/2/things/vehicle-21/features/OBD
curl http://localhost:8080/api/2/things/vehicle-21/features/Safety
curl http://localhost:8080/api/2/things/vehicle-21/features/Diagnostics
```

## Functional Modification

Overheat Safety Constraint: When CoolantTemperature >= 110C, adapter sets OverheatActive=true, FaultCode="ENGINE_OVERHEAT", SafetyConstraintActive=true, and logs to FaultHistory. Clears when temp < 105C (hysteresis).

## Testing

Monitor adapter:
```bash
docker-compose logs -f ditto-adapter
```

Check data in Ditto while simulator runs:
```bash
curl http://localhost:8080/api/2/things/vehicle-21/features/OBD | jq .
curl http://localhost:8080/api/2/things/vehicle-21/features/Safety | jq .
```

Check MongoDB:
```bash
docker-compose exec mongo mongosh -u ditto -p ditto ditto
db.things.findOne()
```

