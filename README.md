# CAN 

sudo apt update
sudo apt install can-utils

sudo ip link set can0 up type can bitrate 250000
(check with: ip link show can0)

# Setup 
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ODrive (S1)

- firmware
https://docs.odriverobotics.com/releases/firmware

get the flat_endpoints.json for the odrive firmware 

- config restore 
python3 ./can_restore_config.py --channel can0 --node-id 0 --endpoints-json ./flat_endpoints.json --config ./config.json --save-config

- calibrate
python3 ./can_calibrate.py --channel can0 --node-id 0 --save-config

- verify CAN comms
candump can0 -xct z -n 10


# Run it
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000