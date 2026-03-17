import os
import time
import asyncio
from kuksa_client.grpc.aio import VSSClient
from kuksa_client.grpc import Datapoint

# Use environment variable so it works both locally (127.0.0.1) and in Docker (kuksa)
KUKSA_HOST = os.environ.get("KUKSA_HOST", "127.0.0.1")
KUKSA_PORT = int(os.environ.get("KUKSA_PORT", "55555"))

def get_vehicle_state(t):
    state = {
        "speed": 0,
        "steeringAngle": 0,
        "batteryLevel": 95,
        "engineTemperature": 80
    }

    # Phase 1: Idle
    if 0 <= t <= 5:
        state["speed"] = 0
        state["steeringAngle"] = 0
        state["batteryLevel"] = 95
        state["engineTemperature"] = 80

    # Phase 2: Accelerating
    elif 6 <= t <= 12:
        state["speed"] = 10 + (t - 6) * 7
        state["steeringAngle"] = 1
        state["batteryLevel"] = 95 - (t - 6) * 0.3
        state["engineTemperature"] = 85 + (t - 6) * 1.5

    # Phase 3: Turning
    elif 13 <= t <= 18:
        state["speed"] = 40
        state["steeringAngle"] = 15 if t < 16 else -10
        state["batteryLevel"] = 93 - (t - 13) * 0.2
        state["engineTemperature"] = 95

    # Phase 4: Cruising
    elif 19 <= t <= 24:
        state["speed"] = 55
        state["steeringAngle"] = 0
        state["batteryLevel"] = 92 - (t - 19) * 0.2
        state["engineTemperature"] = 100

    # Phase 5: Overheat fault
    elif 25 <= t <= 30:
        state["speed"] = 50
        state["steeringAngle"] = 0
        state["batteryLevel"] = 91 - (t - 25) * 0.2
        state["engineTemperature"] = 110 + (t - 25) * 2

    # Phase 6: Safety slowdown
    elif 31 <= t <= 36:
        state["speed"] = max(20, 50 - (t - 31) * 6)
        state["steeringAngle"] = 0
        state["batteryLevel"] = 89
        state["engineTemperature"] = 118

    return state

async def main():
    print(f"[Simulator] Connecting to Kuksa at {KUKSA_HOST}:{KUKSA_PORT} ...")
    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        print("[Simulator] Connected. Starting 36-second simulation sequence.")

        for t in range(0, 37):
            print(f'Time = {t}')
            state = get_vehicle_state(t)

            Speed = state["speed"]
            SteeringAngle = state["steeringAngle"]
            EngineTemperature = state["engineTemperature"]
            BatteryLevel = state["batteryLevel"]

            await client.set_current_values({
                'Vehicle.OBD.VehicleSpeed': Datapoint(Speed),
                'Vehicle.OBD.ThrottlePosition': Datapoint(SteeringAngle),
                'Vehicle.OBD.CoolantTemperature': Datapoint(EngineTemperature),
                'Vehicle.OBD.EngineSpeed': Datapoint(BatteryLevel),
            })

            print(f'Vehicle Speed = {Speed}')
            print(f'Engine Temperature = {EngineTemperature}')
            print(f'Steering Angle = {SteeringAngle}')
            print(f'Battery Level = {BatteryLevel}')

            time.sleep(1)
            print('-----------------------------')

        print('End of Sequence')

asyncio.run(main())