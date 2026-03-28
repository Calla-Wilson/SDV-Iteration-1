import json
import asyncio
import os
import time
import zenoh
from kuksa_client.grpc.aio import VSSClient
from kuksa_client.grpc import Datapoint

KUKSA_HOST = "kuksa"
KUKSA_PORT = 55555

ZENOH_TOPIC = "vehicle/vehicle-21/telemetry"

VSS_PATHS = [
    "Vehicle.OBD.VehicleSpeed",        # -> speed
    "Vehicle.OBD.ThrottlePosition",    # -> steeringAngle
    "Vehicle.OBD.CoolantTemperature",  # -> engineTemperature
    "Vehicle.OBD.EngineSpeed",         # -> batteryLevel
]

# FUNCTIONAL MODIFICATION (Iteration 1): overheat safety threshold (degrees Celsius).
# When CoolantTemperature reaches or exceeds this value the bridge tags
# the outgoing payload so Ditto / OpenSOVD can trigger alerts or rules.
OVERHEAT_THRESHOLD = 110.0

# ITERATION 2 EXTENSION: Configurable network delay injection (milliseconds).
# Simulates real-world network latency in vehicle-to-cloud communication.
# Set via the ZENOH_DELAY_MS environment variable in docker-compose.yml.
# Default is 0 (no delay). Example: ZENOH_DELAY_MS=200 adds 200ms delay
# before each Zenoh publish to simulate cellular or satellite network lag.
ZENOH_DELAY_MS = int(os.environ.get("ZENOH_DELAY_MS", "0"))


def build_payload(values: dict) -> dict:
    """
    Convert a Kuksa get_current_values result dict into the canonical
    telemetry payload published on Zenoh.
    """
    speed      = _val(values, "Vehicle.OBD.VehicleSpeed")
    steer      = _val(values, "Vehicle.OBD.ThrottlePosition")
    temp       = _val(values, "Vehicle.OBD.CoolantTemperature")
    batt       = _val(values, "Vehicle.OBD.EngineSpeed")

    # Overheat fault detection (functional modification)
    fault_active = temp is not None and temp >= OVERHEAT_THRESHOLD
    fault_code   = "ENGINE_OVERHEAT" if fault_active else None

    return {
        "vehicleId": "vehicle-21",
        "timestamp": time.time(),
        "telemetry": {
            "speed":             speed,
            "steeringAngle":     steer,
            "engineTemperature": temp,
            "batteryLevel":      batt,
        },
        "fault_active": fault_active,
        "fault_code":   fault_code,
    }


def _val(values: dict, path: str):
    """Safely extract a float value from a Kuksa datapoint dict."""
    dp = values.get(path)
    if dp is None:
        return None
    v = dp.value
    return round(float(v), 3) if v is not None else None


async def main():
    print(f"[KuksaToZenoh] Connecting to Kuksa at {KUKSA_HOST}:{KUKSA_PORT} ...")
    print(f"[KuksaToZenoh] Network delay injection: {ZENOH_DELAY_MS} ms")

    # Open Zenoh session (default peer-to-peer config; resolves to the
    # zenoh container on the same Docker network)
    z_session = zenoh.open(zenoh.Config())
    publisher  = z_session.declare_publisher(ZENOH_TOPIC)
    print(f"[KuksaToZenoh] Zenoh publisher declared on topic: {ZENOH_TOPIC}")

    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        print("[KuksaToZenoh] Connected to Kuksa. Polling for updates ...")

        prev_temp = None

        # Poll every second so we stay in sync with the 1 Hz simulator
        while True:
            try:
                values = await client.get_current_values(VSS_PATHS)
                payload = build_payload(values)

                # Only publish when at least one value is present
                if any(v is not None for v in payload["telemetry"].values()):

                    # ITERATION 2: Inject configurable delay before publishing
                    # to simulate real-world network latency (cellular, satellite, etc.)
                    if ZENOH_DELAY_MS > 0:
                        await asyncio.sleep(ZENOH_DELAY_MS / 1000.0)

                    msg = json.dumps(payload)
                    publisher.put(msg)

                    temp = payload["telemetry"]["engineTemperature"]

                    # Log fault transitions
                    if payload["fault_active"] and prev_temp is not None and prev_temp < OVERHEAT_THRESHOLD:
                        print(
                            f"[KuksaToZenoh] *** FAULT DETECTED: {payload['fault_code']} "
                            f"(temp={temp} C >= threshold={OVERHEAT_THRESHOLD} C) ***"
                        )

                    # Include delay info in log output for visibility
                    delay_info = f" | delay={ZENOH_DELAY_MS}ms" if ZENOH_DELAY_MS > 0 else ""
                    print(
                        f"[KuksaToZenoh] Published -> "
                        f"speed={payload['telemetry']['speed']} km/h | "
                        f"steer={payload['telemetry']['steeringAngle']} | "
                        f"temp={temp} C | "
                        f"batt={payload['telemetry']['batteryLevel']}%"
                        f"{delay_info} | "
                        f"fault={payload['fault_active']}"
                    )
                    prev_temp = temp

            except Exception as exc:
                print(f"[KuksaToZenoh] Error reading from Kuksa: {exc}")

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())