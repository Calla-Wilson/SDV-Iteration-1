import time
import asyncio
from kuksa_client.grpc.aio import VSSClient
from kuksa_client.grpc import Datapoint

KUKSA_HOST = "kuksa"
KUKSA_PORT = 55555


def get_vehicle_state(t):
    """Return a dict of vehicle signal values for simulation second t."""

    # Phase 1: Idle
    if 0 <= t <= 5:
        return {
            "speed":             0.0,
            "steeringAngle":     0.0,
            "batteryLevel":      95.0,
            "engineTemperature": 80.0,
        }

    # Phase 2: Accelerating
    elif 6 <= t <= 12:
        return {
            "speed":             10.0 + (t - 6) * 7.0,
            "steeringAngle":     1.0,
            "batteryLevel":      95.0 - (t - 6) * 0.3,
            "engineTemperature": 85.0 + (t - 6) * 1.5,
        }

    # Phase 3: Turning
    elif 13 <= t <= 18:
        return {
            "speed":             40.0,
            "steeringAngle":     15.0 if t < 16 else -10.0,
            "batteryLevel":      93.0 - (t - 13) * 0.2,
            "engineTemperature": 95.0,
        }

    # Phase 4: Cruising
    elif 19 <= t <= 24:
        return {
            "speed":             55.0,
            "steeringAngle":     0.0,
            "batteryLevel":      92.0 - (t - 19) * 0.2,
            "engineTemperature": 100.0,
        }

    # Phase 5: Overheat fault injection (FUNCTIONAL MODIFICATION)
    # Engine temperature exceeds the safe threshold (>= 110 C).
    # Temperature climbs 2 C/s, peaking at 120 C at t=30.
    # This models the sensor-fault scenario from the project proposal.
    elif 25 <= t <= 30:
        return {
            "speed":             50.0,
            "steeringAngle":     0.0,
            "batteryLevel":      91.0 - (t - 25) * 0.2,
            "engineTemperature": 110.0 + (t - 25) * 2.0,
        }

    # Phase 6: Safety slowdown (triggered by overheat detection)
    elif 31 <= t <= 36:
        return {
            "speed":             max(20.0, 50.0 - (t - 31) * 6.0),
            "steeringAngle":     0.0,
            "batteryLevel":      89.0,
            "engineTemperature": 118.0,
        }

    return {
        "speed": 0.0, "steeringAngle": 0.0,
        "batteryLevel": 0.0, "engineTemperature": 0.0,
    }


async def main():
    print(f"[VehicleSource] Connecting to Kuksa at {KUKSA_HOST}:{KUKSA_PORT} ...")

    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        print("[VehicleSource] Connected. Starting simulation (t=0 to t=36).")

        for t in range(0, 37):
            state = get_vehicle_state(t)

            if t <= 5:
                phase = "IDLE"
            elif t <= 12:
                phase = "ACCELERATING"
            elif t <= 18:
                phase = "TURNING"
            elif t <= 24:
                phase = "CRUISING"
            elif t <= 30:
                phase = "OVERHEAT_FAULT"
            else:
                phase = "SAFETY_SLOWDOWN"

            # Push all four OBD signals into the Kuksa Databroker
            await client.set_current_values({
                "Vehicle.OBD.VehicleSpeed":       Datapoint(float(state["speed"])),
                "Vehicle.OBD.ThrottlePosition":   Datapoint(float(state["steeringAngle"])),
                "Vehicle.OBD.CoolantTemperature": Datapoint(float(state["engineTemperature"])),
                "Vehicle.OBD.EngineSpeed":        Datapoint(float(state["batteryLevel"])),
            })

            print(
                f"[VehicleSource] t={t:02d}s [{phase:16s}] "
                f"speed={state['speed']:5.1f} km/h | "
                f"steer={state['steeringAngle']:6.1f} | "
                f"temp={state['engineTemperature']:6.1f} C | "
                f"batt={state['batteryLevel']:5.1f}%"
            )

            time.sleep(1)

        print("[VehicleSource] Simulation complete.")


if __name__ == "__main__":
    asyncio.run(main())
