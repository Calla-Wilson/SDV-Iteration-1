#!/usr/bin/env python3
"""
Ditto Adapter: Zenoh → Ditto Bridge

This adapter listens to vehicle telemetry data from Zenoh and updates
the Eclipse Ditto digital twin. It bridges the communication layer
(Zenoh) to the backend state management layer (Ditto).

Data flow:
  Kuksa → Zenoh (topic: vehicle/vehicle-21/telemetry)
       → Ditto Adapter (this script)
       → Ditto Thing (vehicle-21)
       → REST APIs & Diagnostics
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

import requests
import zenoh

# ============================================================================
# Configuration
# ============================================================================

ZENOH_TOPIC = "vehicle/vehicle-21/telemetry"
DITTO_BASE_URL = "http://ditto:8080/api/2/things"
THING_ID = "vehicle-21"

# Safety thresholds (same as defined in VSS_Ditto.json and kuksa_to_zenoh.py)
OVERHEAT_THRESHOLD = 110.0
OVERHEAT_HYSTERESIS = 5.0  # Temperature range for fault recovery

# Timeouts and retries
DITTO_TIMEOUT = 5.0
DITTO_RETRY_ATTEMPTS = 3
DITTO_RETRY_DELAY = 2.0

# Logging configuration
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
        """Check if overheat fault should be activated (transition from normal to overheat)."""
        if self.last_temperature is None:
            self.last_temperature = current_temp
            return False
        
        # Trigger if crossing threshold upward
        triggered = (self.last_temperature < OVERHEAT_THRESHOLD and 
                    current_temp >= OVERHEAT_THRESHOLD)
        self.last_temperature = current_temp
        return triggered
    
    def should_recover_from_overheat(self, current_temp: float) -> bool:
        """Check if overheat fault should be cleared (hysteresis-based recovery)."""
        return current_temp < (OVERHEAT_THRESHOLD - OVERHEAT_HYSTERESIS)


# Global state instance
ditto_state = DittoState()

# ============================================================================
# Ditto API Functions
# ============================================================================

def _ditto_put(endpoint: str, data: Dict[str, Any]) -> bool:
    """
    PUT data to Ditto with retries.
    
    Args:
        endpoint: Ditto API endpoint path (e.g., "/features/OBD/properties/VehicleSpeed")
        data: Dictionary with "value" key
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{DITTO_BASE_URL}/{THING_ID}{endpoint}"
    
    for attempt in range(DITTO_RETRY_ATTEMPTS):
        try:
            response = requests.put(
                url,
                json=data,
                timeout=DITTO_TIMEOUT,
                headers={"Content-Type": "application/json"}
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


def _ditto_patch(endpoint: str, data: Dict[str, Any]) -> bool:
    """
    PATCH data to Ditto (for updating multiple properties at once).
    
    Args:
        endpoint: Ditto API endpoint path
        data: Dictionary to merge into target
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{DITTO_BASE_URL}/{THING_ID}{endpoint}"
    
    try:
        response = requests.patch(
            url,
            json=data,
            timeout=DITTO_TIMEOUT,
            headers={"Content-Type": "application/json"}
        )
        return response.status_code in [200, 201, 204]
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ditto PATCH error: {e}")
        return False


def update_obd_telemetry(telemetry: Dict[str, float]) -> bool:
    """
    Update OBD feature with telemetry values.
    
    Args:
        telemetry: Dict with speed, steeringAngle, engineTemperature, batteryLevel
    
    Returns:
        True if all updates successful
    """
    success = True
    
    # Map telemetry keys to Ditto OBD properties
    mappings = {
        "speed": "VehicleSpeed",
        "steeringAngle": "ThrottlePosition",
        "engineTemperature": "CoolantTemperature",
        "batteryLevel": "EngineSpeed"
    }
    
    for telemetry_key, ditto_key in mappings.items():
        if telemetry_key in telemetry:
            value = telemetry[telemetry_key]
            if not _ditto_put(
                f"/features/OBD/properties/{ditto_key}",
                {"value": value}
            ):
                logger.error(f"Failed to update OBD.{ditto_key}")
                success = False
    
    # Update telemetry metadata
    timestamp = datetime.utcnow().isoformat() + "Z"
    _ditto_put("/features/Telemetry/properties/lastUpdate", {"value": timestamp})
    
    return success


def update_safety_constraints(
    overheat_active: bool,
    fault_code: str,
    safety_constraint_active: bool
) -> bool:
    """
    Update Safety feature with fault state.
    
    Args:
        overheat_active: Whether overheat fault is active
        fault_code: Fault code string (e.g., "ENGINE_OVERHEAT" or "")
        safety_constraint_active: Whether safety constraint is enforced
    
    Returns:
        True if update successful
    """
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    success = True
    
    if not _ditto_put("/features/Safety/properties/OverheatActive", 
                      {"value": overheat_active}):
        logger.error("Failed to update Safety.OverheatActive")
        success = False
    
    if not _ditto_put("/features/Safety/properties/FaultCode", 
                      {"value": fault_code}):
        logger.error("Failed to update Safety.FaultCode")
        success = False
    
    if overheat_active:
        if not _ditto_put("/features/Safety/properties/LastFaultTime", 
                          {"value": timestamp}):
            logger.error("Failed to update Safety.LastFaultTime")
            success = False
    
    if not _ditto_put("/features/Safety/properties/SafetyConstraintActive", 
                      {"value": safety_constraint_active}):
        logger.error("Failed to update Safety.SafetyConstraintActive")
        success = False
    
    return success


def update_diagnostics(
    system_health: str,
    fault_event: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Update Diagnostics feature with health status and fault history.
    
    Args:
        system_health: "OK", "WARNING", or "CRITICAL"
        fault_event: Optional fault event to append to history
    
    Returns:
        True if update successful
    """
    success = True
    
    # Update system health
    if not _ditto_put("/features/Diagnostics/properties/SystemHealth", 
                      {"value": system_health}):
        logger.error("Failed to update Diagnostics.SystemHealth")
        success = False
    
    # Update data timestamp
    timestamp = datetime.utcnow().isoformat() + "Z"
    _ditto_put("/features/Diagnostics/properties/LastDataUpdateTime", 
              {"value": timestamp})
    
    # Increment update counter
    ditto_state.update_count += 1
    _ditto_put("/features/Diagnostics/properties/DataUpdateCount", 
              {"value": ditto_state.update_count})
    
    # Append fault event if provided
    if fault_event:
        ditto_state.fault_history.append(fault_event)
        # Keep only last 100 events
        if len(ditto_state.fault_history) > 100:
            ditto_state.fault_history = ditto_state.fault_history[-100:]
        
        _ditto_put("/features/Diagnostics/properties/FaultHistory", 
                  {"value": ditto_state.fault_history})
    
    return success


# ============================================================================
# Safety Rules Engine
# ============================================================================

def evaluate_safety_rules(
    temperature: float,
    fault_active_upstream: bool,
    fault_code_upstream: str
) -> tuple[bool, str, bool, str]:
    """
    Evaluate safety rules and return the desired state.
    
    Rules:
    1. Overheat Detection: If temp >= OVERHEAT_THRESHOLD, set OverheatActive=true
    2. Safety Constraint: If OverheatActive, set SafetyConstraintActive=true
    3. Fault Recovery: If temp < OVERHEAT_THRESHOLD - HYSTERESIS, clear fault
    
    Args:
        temperature: Current coolant temperature (°C)
        fault_active_upstream: Fault flag from Zenoh/Kuksa
        fault_code_upstream: Fault code from Zenoh/Kuksa
    
    Returns:
        Tuple of (overheat_active, fault_code, safety_constraint_active, system_health)
    """
    
    overheat_active = ditto_state.overheat_active
    fault_code = ""
    safety_constraint_active = False
    system_health = "OK"
    
    # Rule 1: Detect overheat condition
    if temperature >= OVERHEAT_THRESHOLD:
        # Overheat condition detected
        overheat_active = True
        fault_code = "ENGINE_OVERHEAT"
        system_health = "CRITICAL"
        
        # Log if this is a new fault (transition)
        if ditto_state.was_overheat_triggered(temperature):
            logger.warning(
                f"⚠️  OVERHEAT FAULT DETECTED: Temperature {temperature}°C "
                f">= threshold {OVERHEAT_THRESHOLD}°C"
            )
    
    # Rule 3: Recover from overheat (hysteresis)
    elif ditto_state.should_recover_from_overheat(temperature):
        # Temperature normalized, clear fault
        if overheat_active:
            logger.info(
                f"✓ Overheat fault cleared: Temperature {temperature}°C "
                f"< threshold {OVERHEAT_THRESHOLD - OVERHEAT_HYSTERESIS}°C"
            )
        overheat_active = False
        fault_code = ""
        system_health = "OK"
    
    # Rule 2: Activate safety constraint if fault is active
    if overheat_active:
        safety_constraint_active = True
        if system_health == "OK":
            system_health = "WARNING"
    
    # Update state
    ditto_state.overheat_active = overheat_active
    ditto_state.system_health = system_health
    
    return overheat_active, fault_code, safety_constraint_active, system_health


# ============================================================================
# Zenoh Message Handler
# ============================================================================

def on_zenoh_sample(sample):
    """
    Callback function invoked when a Zenoh message is received.
    
    Expected message format (from kuksa_to_zenoh.py):
    {
        "vehicleId": "vehicle-21",
        "timestamp": <unix_timestamp>,
        "telemetry": {
            "speed": <float>,
            "steeringAngle": <float>,
            "engineTemperature": <float>,
            "batteryLevel": <float>
        },
        "fault_active": <bool>,
        "fault_code": <string>
    }
    """
    try:
        # Parse Zenoh message
        message = sample.value.payload.to_string()
        payload = json.loads(message)
        
        logger.debug(f"Received Zenoh message: {message[:100]}...")
        
        # Extract fields
        telemetry = payload.get("telemetry", {})
        temperature = telemetry.get("engineTemperature")
        fault_active_upstream = payload.get("fault_active", False)
        fault_code_upstream = payload.get("fault_code", "")
        timestamp = payload.get("timestamp")
        
        # Validate required fields
        if temperature is None:
            logger.warning("Received message without engineTemperature")
            return
        
        # ===== EVALUATE SAFETY RULES =====
        overheat_active, fault_code, safety_constraint_active, system_health = \
            evaluate_safety_rules(temperature, fault_active_upstream, fault_code_upstream)
        
        # ===== UPDATE DITTO STATE =====
        
        # 1. Update OBD telemetry
        if not update_obd_telemetry(telemetry):
            logger.warning("Failed to update OBD telemetry")
        
        # 2. Update Safety constraints
        if not update_safety_constraints(overheat_active, fault_code, safety_constraint_active):
            logger.warning("Failed to update Safety constraints")
        
        # 3. Create fault event if needed
        fault_event = None
        if overheat_active and ditto_state.was_overheat_triggered(temperature):
            fault_event = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "fault_code": fault_code,
                "temperature": round(temperature, 2),
                "severity": "CRITICAL"
            }
        
        # 4. Update Diagnostics
        if not update_diagnostics(system_health, fault_event):
            logger.warning("Failed to update Diagnostics")
        
        # ===== LOG UPDATE =====
        logger.info(
            f"✓ Updated vehicle-21 | "
            f"Speed={telemetry.get('speed')} km/h | "
            f"Temp={temperature}°C | "
            f"Overheat={overheat_active} | "
            f"Health={system_health}"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Zenoh message: {e}")
    except KeyError as e:
        logger.error(f"Missing required field in message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in Zenoh callback: {e}", exc_info=True)


# ============================================================================
# Ditto Thing Initialization
# ============================================================================

def initialize_ditto_thing() -> bool:
    """
    Create or verify the Ditto Thing exists.
    
    Returns:
        True if Thing exists or was created successfully
    """
    # Try to get the Thing
    try:
        response = requests.get(
            f"{DITTO_BASE_URL}/{THING_ID}",
            timeout=DITTO_TIMEOUT
        )
        
        if response.status_code == 200:
            logger.info(f"✓ Ditto Thing '{THING_ID}' already exists")
            return True
    except requests.exceptions.RequestException:
        pass
    
    # If not found, try to create it
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
            json=thing_definition,
            timeout=DITTO_TIMEOUT,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"✓ Created Ditto Thing '{THING_ID}'")
            return True
        else:
            logger.error(f"Failed to create Thing: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create Thing: {e}")
        return False


async def wait_for_ditto(max_retries: int = 10, delay: float = 2.0) -> bool:
    """
    Wait for Ditto to be available with retries.
    
    Args:
        max_retries: Maximum number of retries
        delay: Delay between retries in seconds
    
    Returns:
        True if Ditto is available
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(
                f"{DITTO_BASE_URL}/{THING_ID}",
                timeout=DITTO_TIMEOUT
            )
            if response.status_code in [200, 404]:  # 404 is OK (Thing doesn't exist yet)
                logger.info("✓ Ditto is available")
                return True
        except requests.exceptions.RequestException:
            pass
        
        logger.info(f"Waiting for Ditto... (attempt {attempt + 1}/{max_retries})")
        await asyncio.sleep(delay)
    
    return False


# ============================================================================
# Main Zenoh Subscriber Loop
# ============================================================================

async def main():
    """Main function: connect to Zenoh and listen for vehicle data."""
    
    logger.info("=" * 70)
    logger.info("Ditto Adapter Starting")
    logger.info("=" * 70)
    logger.info(f"Zenoh Topic: {ZENOH_TOPIC}")
    logger.info(f"Ditto URL: {DITTO_BASE_URL}/{THING_ID}")
    logger.info(f"Overheat Threshold: {OVERHEAT_THRESHOLD}°C")
    logger.info("=" * 70)
    
    # Wait for Ditto to be available
    logger.info("Checking Ditto availability...")
    if not await wait_for_ditto():
        logger.error("❌ Ditto is not available. Exiting.")
        return
    
    # Initialize Ditto Thing
    if not initialize_ditto_thing():
        logger.warning("Failed to initialize Thing, but continuing anyway...")
    
    # Connect to Zenoh
    logger.info(f"Connecting to Zenoh...")
    try:
        config = zenoh.Config()
        session = zenoh.open(config)
        logger.info("✓ Connected to Zenoh")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Zenoh: {e}")
        return
    
    # Subscribe to vehicle telemetry topic
    logger.info(f"Subscribing to topic: {ZENOH_TOPIC}")
    try:
        sub = session.declare_subscriber(ZENOH_TOPIC, on_zenoh_sample)
        logger.info("✓ Subscribed to vehicle telemetry")
    except Exception as e:
        logger.error(f"❌ Failed to subscribe: {e}")
        session.close()
        return
    
    # Run indefinitely
    logger.info("Listening for vehicle data... (press Ctrl+C to stop)")
    logger.info("=" * 70)
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        session.close()
        logger.info("Ditto Adapter stopped")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    asyncio.run(main())
