Installations
https://docs.docker.com/desktop/setup/install/windows-install/ - Docker
https://gitforwindows.org/ - Git
https://visualstudio.microsoft.com/visual-cpp-build-tools/ - MS build tools
Python path variable to /scripts and another to /bin

Initial steps
Download the folder “files for iteration 1”
Open powershell
Cd <path/to/folder> into the folder
git clone https://github.com/eclipse-kuksa/kuksa-databroker
To create kuksa-databroker 
Move the OBD file from “files for iteration 1” to kuksa-databroker
Create a folder called kuksa-ditto inside kuksa-databroker
Move everything from “ditto files” into kuksa-ditto

Need 3 powershell terminal windows (not cmd terminal)
1st window launch docker container
cd ‘path\to\kuksa-databroker’
Open docker
<  	docker run --rm -it -p 55555:55555 -v "$(pwd)/OBD.json:/OBD.json" ghcr.io/eclipse-kuksa/kuksa-databroker:main --insecure --vss /OBD.json  	   >
-This creates the docker container, it’ll show up in the docker app (required)
-The docker app can be used to close the container but if you just close the powershell window with the container it will close

2nd window To create the virtual environment
Cd ‘path\to\kuksa-ditto’
python3 -m venv venv
- a folder called venv should appear in kuksa-ditto
<	. ‘path\to\kuksa-ditto\venv\Scripts\Activate.ps1’   	>
- this will enter the virtual environment
pip install kuksa-client
pip install requests
-These two need to be installed in the virtual environment

2nd window continued (in virtual env) the send obd data
cd  ‘path\to\kuksa-databroker\kuksa-ditto’
<	. ‘path\to\kuksa-ditto\venv\Scripts\Activate.ps1’   	>
python send_obd_data_to_kuksa.py
-This one will run for 36 seconds then stop
-Can be canceled early with ctrl c

3rd window (in virtual env) the retrieve obd data
cd  ‘path\to\kuksa-databroker\kuksa-ditto’
<	. ‘path\to\kuksa-ditto\venv\Scripts\Activate.ps1’   	>
python retrieve_obd_data_from_kuksa.py
-This one will run forever, if it is activated before the send obd data it will just use the last set of data transmitted
-Can be canceled with ctrl c




This is the guide the TA provided and will help get the data into ditto
https://github.com/zubxxr/Vehicle-Data-Simulation-and-Visualization?tab=readme-ov-file#task-3-sending-obd-data-to-kuksa-databroker


