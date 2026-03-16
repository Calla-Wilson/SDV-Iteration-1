import asyncio
from kuksa_client.grpc.aio import VSSClient
import time

# Asynchronous main function to connect to Kuksa Databroker and retrieve OBD data
async def main():
	
	# Establish an asynchronous connection to the Kuksa Databroker at the IP: 127.0.0.1 and port 55555
	async with VSSClient('127.0.0.1' , 55555) as client:

		# Repeat Infinitely
		while True:
			# Retrieve the current values of the specified OBD features from the Databroker
			values = await client.get_current_values([
				'Vehicle.OBD.VehicleSpeed', 'Vehicle.OBD.EngineSpeed' ,
				'Vehicle.OBD.ThrottlePosition' , 'Vehicle.OBD.CoolantTemperature'
			])

			# Extract the individual feature values from the retrieved data
			Speed = values['Vehicle.OBD.VehicleSpeed'].value
			BatteryLevel = values['Vehicle.OBD.EngineSpeed'].value
			SteeringAngle = values['Vehicle.OBD.ThrottlePosition'].value
			EngineTemperature = values['Vehicle.OBD.CoolantTemperature'].value

			# Print the value for each feature
			print('Speed = ' , round(Speed, 2))
			print('Engine Temperature = ' , round(EngineTemperature, 2))
			print('Steering Angle = ' , round(SteeringAngle, 2))
			print('Battery Level = ' , round(BatteryLevel, 2))
			

			# Pause for 1 second
			time.sleep(1)

			print('-----------------------------')

# Run the asynchronous main function
asyncio.run(main())