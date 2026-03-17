#!/usr/bin/env python3
"""
Ditto Adapter: Zenoh -> Ditto Bridge

This adapter listens to vehicle telemetry data from Zenoh and updates
the Eclipse Ditto digital twin. It bridges the communication layer
(Zenoh) to the backend state management layer (Ditto).

Data flow:
  Kuksa -> Zenoh (topic: vehicle/vehicle-21/telemetry)
       -> Ditto Adapter (this script)
       -> Ditto Thing (vehicle-21)
       -> REST APIs & Diagnostics
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

import requests
import zenoh

# ============================================================================
# Configuration (read from env vars for Docker, with sensible defaults)
# ============================================================================

ZENOH_TOPIC = os.environ.get("ZENOH_TOPIC", "vehicle/vehicle-21/telemetry")
DITTO_BASE_URL = os.environ.get("DITTO_BASE_URL", "http://ditto-nginx:80/api/2/things")
THING_ID = "vehicle-21"
DITTO_AUTH = ("devops", "foobar")

# Safety thresholds
OVERHEAT_THRESHOLD = 110.0
OVERHEAT_HYSTERESIS = 5.0

# Timeouts and retries
DITTO_TIMEOUT = 5.0
DITTO_RETRY_ATTEMPTS = 3
DITTO_RETRY_DELAY = 2.0

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [Ditto Adapter] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Global State Tracking
# ============================================================================

class DittoState:
    """Tracks the last known state to detect changes and manage fault history."""

    def __init__(self):
        self.last_temperature: Optional[float] = None
        self.overheat_active: bool = False
        self.fault_history: list = []
        self.update_count: int = 0
        self.system_health: str = "OK"

    def was_overheat_triggered(self, current_temp: float) -> bool:
        if self.last_temperature is None:
            self.last_temperature = current_temp
            return False
        triggered = (self.last_temperature < OVERHEAT_THRESHOLD and
                    current_temp >= OVERHEAT_THRESHOLD)
        self.last_temperature = current_temp
        return triggered

    def should_recover_from_overheat(self, current_temp: float) -> bool:
        return current_temp < (OVERHEAT_THRESHOLD - OVERHEAT_HYSTERESIS)


ditto_state = DittoState()

# ============================================================================
# Ditto API Functions
# ============================================================================

def _ditto_put(endpoint: str, data: Dict[str, Any]) -> bool:
    url = f"{DITTO_BASE_URL}/{THING_ID}{endpoint}"

    for attempt in range(DITTO_RETRY_ATTEMPTS):
        try:
            response = requests.put(
                url, json=data, timeout=DITTO_TIMEOUT,
                headers={"Content-Type": "application/json"},
                auth=DITTO_AUTH
            )
            if response.status_code in [200, 201, 204]:
                return True
            else:
                logger.warning(
                    f"Ditto PUT failed (attempt {attempt + 1}): "
                    f"{response.status_code} - {response.text[:100]}"
                )
        except requests.exceptions.RequestException as e:
            logger.warning(f"Ditto connection error (attempt {attempt + 1}): {e}")

        if attempt < DITTO_RETRY_ATTEMPTS - 1:
            time.sleep(DITTO_RETRY_DELAY)

    return False


def update_obd_telemetry(telemetry: Dict[str, float]) -> bool:
    success = True
    mappings = {
        "speed": "VehicleSpeed",
        "steeringAngle": "ThrottlePosition",
        "engineTemperature": "CoolantTemperature",
        "batteryLevel": "EngineSpeed"
    }

    for telemetry_key, ditto_key in mappings.items():
        if telemetry_key in telemetry:
            value = telemetry[telemetry_key]
            if not _ditto_put(f"/features/OBD/properties/{ditto_key}", {"value": value}):
                logger.error(f"Failed to update OBD.{ditto_key}")
                success = False

    timestamp = datetime.utcnow().isoformat() + "Z"
    _ditto_put("/features/Telemetry/properties/lastUpdate", {"value": timestamp})

    return success


def update_safety_constraints(overheat_active, fault_code, safety_constraint_active):
    timestamp = datetime.utcnow().isoformat() + "Z"
    success = True

    if not _ditto_put("/features/Safety/properties/OverheatActive", {"value": overheat_active}):
        success = False
    if not _ditto_put("/features/Safety/properties/FaultCode", {"value": fault_code}):
        success = False
    if overheat_active:
        _ditto_put("/features/Safety/properties/LastFaultTime", {"value": timestamp})
    if not _ditto_put("/features/Safety/properties/SafetyConstraintActive", {"value": safety_constraint_active}):
        success = False

    return success


def update_diagnostics(system_health, fault_event=None):
    success = True

    if not _ditto_put("/features/Diagnostics/properties/SystemHealth", {"value": system_health}):
        success = False

    timestamp = datetime.utcnow().isoformat() + "Z"
    _ditto_put("/features/Diagnostics/properties/LastDataUpdateTime", {"value": timestamp})

    ditto_state.update_count += 1
    _ditto_put("/features/Diagnostics/properties/DataUpdateCount", {"value": ditto_state.update_count})

    if fault_event:
        ditto_state.fault_history.append(fault_event)
        if len(ditto_state.fault_history) > 100:
            ditto_state.fault_history = ditto_state.fault_history[-100:]
        _ditto_put("/features/Diagnostics/properties/FaultHistory", {"value": ditto_state.fault_history})

    return success


# ============================================================================
# Safety Rules Engine
# ============================================================================

def evaluate_safety_rules(temperature, fault_active_upstream, fault_code_upstream):
    overheat_active = ditto_state.overheat_active
    fault_code = ""
    safety_constraint_active = False
    system_health = "OK"

    if temperature >= OVERHEAT_THRESHOLD:
        overheat_active = True
        fault_code = "ENGINE_OVERHEAT"
        system_health = "CRITICAL"

        if ditto_state.was_overheat_triggered(temperature):
            logger.warning(
                f"OVERHEAT FAULT DETECTED: Temperature {temperature} C "
                f">= threshold {OVERHEAT_THRESHOLD} C"
            )
    elif ditto_state.should_recover_from_overheat(temperature):
        if overheat_active:
            logger.info(
                f"Overheat fault cleared: Temperature {temperature} C "
                f"< threshold {OVERHEAT_THRESHOLD - OVERHEAT_HYSTERESIS} C"
            )
        overheat_active = False
        fault_code = ""
        system_health = "OK"

    if overheat_active:
        safety_constraint_active = True
        if system_health == "OK":
            system_health = "WARNING"

    ditto_state.overheat_active = overheat_active
    ditto_state.system_health = system_health

    return overheat_active, fault_code, safety_constraint_active, system_health


# ============================================================================
# Zenoh Message Handler
# ============================================================================

def on_zenoh_sample(sample):
    try:
        message = sample.value.payload.to_string()
        payload = json.loads(message)

        telemetry = payload.get("telemetry", {})
        temperature = telemetry.get("engineTemperature")
        fault_active_upstream = payload.get("fault_active", False)
        fault_code_upstream = payload.get("fault_code", "")

        if temperature is None:
            logger.warning("Received message without engineTemperature")
            return

        overheat_active, fault_code, safety_constraint_active, system_health = \
            evaluate_safety_rules(temperature, fault_active_upstream, fault_code_upstream)

        update_obd_telemetry(telemetry)
        update_safety_constraints(overheat_active, fault_code, safety_constraint_active)

        fault_event = None
        if overheat_active and ditto_state.was_overheat_triggered(temperature):
            fault_event = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "fault_code": fault_code,
                "temperature": round(temperature, 2),
                "severity": "CRITICAL"
            }

        update_diagnostics(system_health, fault_event)

        logger.info(
            f"Updated vehicle-21 | "
            f"Speed={telemetry.get('speed')} km/h | "
            f"Temp={temperature} C | "
            f"Overheat={overheat_active} | "
            f"Health={system_health}"
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Zenoh message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in Zenoh callback: {e}", exc_info=True)


# ============================================================================
# Ditto Thing Initialization
# ============================================================================

def initialize_ditto_thing():
    try:
        response = requests.get(f"{DITTO_BASE_URL}/{THING_ID}", timeout=DITTO_TIMEOUT, auth=DITTO_AUTH)
        if response.status_code == 200:
            logger.info(f"Ditto Thing '{THING_ID}' already exists")
            return True
    except requests.exceptions.RequestException:
        pass

    logger.info(f"Creating Ditto Thing '{THING_ID}'...")

    thing_definition = {
        "thingId": THING_ID,
        "policyId": "org.ovin:my-policy",
        "attributes": {
            "vehicleId": {"value": THING_ID},
            "manufacturer": {"value": "SDV Test Fleet"},
            "model": {"value": "Simulation Vehicle"}
        },
        "features": {}
    }

    try:
        response = requests.put(
            f"{DITTO_BASE_URL}/{THING_ID}",
            json=thing_definition, timeout=DITTO_TIMEOUT,
            headers={"Content-Type": "application/json"},
            auth=DITTO_AUTH
        )
        if response.status_code in [200, 201]:
            logger.info(f"Created Ditto Thing '{THING_ID}'")
            return True
        else:
            logger.error(f"Failed to create Thing: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create Thing: {e}")
        return False


async def wait_for_ditto(max_retries=10, delay=2.0):
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{DITTO_BASE_URL}/{THING_ID}", timeout=DITTO_TIMEOUT, auth=DITTO_AUTH)
            if response.status_code in [200, 404]:
                logger.info("Ditto is available")
                return True
        except requests.exceptions.RequestException:
            pass
        logger.info(f"Waiting for Ditto... (attempt {attempt + 1}/{max_retries})")
        await asyncio.sleep(delay)
    return False


# ============================================================================
# Main
# ============================================================================

async def main():
    logger.info("=" * 70)
    logger.info("Ditto Adapter Starting")
    logger.info(f"Zenoh Topic: {ZENOH_TOPIC}")
    logger.info(f"Ditto URL: {DITTO_BASE_URL}/{THING_ID}")
    logger.info(f"Overheat Threshold: {OVERHEAT_THRESHOLD} C")
    logger.info("=" * 70)

    if not await wait_for_ditto():
        logger.error("Ditto is not available. Exiting.")
        return

    if not initialize_ditto_thing():
        logger.warning("Failed to initialize Thing, but continuing anyway...")

    logger.info("Connecting to Zenoh...")
    try:
        config = zenoh.Config()
        session = zenoh.open(config)
        logger.info("Connected to Zenoh")
    except Exception as e:
        logger.error(f"Failed to connect to Zenoh: {e}")
        return

    logger.info(f"Subscribing to topic: {ZENOH_TOPIC}")
    try:
        sub = session.declare_subscriber(ZENOH_TOPIC, on_zenoh_sample)
        logger.info("Subscribed to vehicle telemetry")
    except Exception as e:
        logger.error(f"Failed to subscribe: {e}")
        session.close()
        return

    logger.info("Listening for vehicle data... (press Ctrl+C to stop)")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        session.close()
        logger.info("Ditto Adapter stopped")


if __name__ == "__main__":
    asyncio.run(main())
