import time
import asyncio
from kuksa_client.grpc.aio import VSSClient
from kuksa_client.grpc import Datapoint

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
# Asynchronous main function to connect to Kuksa Databroker and retrieve OBD data
async def main():
    # Establish an asynchronous connection to the Kuksa Databroker at the IP: 127.0.0.1 and port 55555
    async with VSSClient('127.0.0.1', 55555) as client:

        # Repeat for 36 seconds
            for t in range(0, 37):
                print('Time =  ', t)
                state = get_vehicle_state(t)
                # use state values for each data point
                Speed = state["speed"]
                SteeringAngle = state["steeringAngle"]
                EngineTemperature = state["engineTemperature"]
                BatteryLevel = state["batteryLevel"]
            
                # Send the values to the Kuksa Databroker with the
                # corresponding vehicle data paths using the 'set_current_values' function
              		# Can't figure out how to change the paths but since they just need to pass through data its fine
                    # just dont change the Vehicle.OBD.*** stuff
                values = await client.set_current_values({
                    'Vehicle.OBD.VehicleSpeed': Datapoint(Speed),
                    'Vehicle.OBD.ThrottlePosition': Datapoint(SteeringAngle),
                    'Vehicle.OBD.CoolantTemperature': Datapoint(EngineTemperature),
                    'Vehicle.OBD.EngineSpeed': Datapoint(BatteryLevel),
                })

                # Print the value for each feature
                print('Vehicle Speed = ', Speed)
                print('Engine Temperature = ', EngineTemperature)
                print('Steering Angle = ', SteeringAngle)
                print('Battery Level = ', BatteryLevel)

                # Pause for 1 second
                time.sleep(1)

                print('-----------------------------')
                
				# break the loop after 36 seconds
                if t == 36:
                    print('End of Sequence')
                    break

# Run the main function
asyncio.run(main())
