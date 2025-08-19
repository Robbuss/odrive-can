# Project README

## Overview

This repository provides a FastAPI + WebSocket backend and a Nuxt 3 + Nuxt UI frontend for controlling multiple joints: ODrive S1 motors over CAN and Moteus r4.11 motors over USB/serial CAN.

---

## Prerequisites

### System Setup (Raspberry Pi OS)

```bash
sudo apt update
sudo apt install can-utils                # CAN tools
sudo ip link set can0 up type can bitrate 250000
# verify: ip link show can0

# Dependencies for Moteus GUI / tview
sudo apt install python3-pyside2* python3-serial python3-can python3-matplotlib python3-qtconsole libraspberrypi-dev
```

### Python (Backend)

```bash
cd backend
python3 -m venv .venv                    # create venv
source .venv/bin/activate                # activate
pip install --upgrade pip
pip install -r requirements.txt          # install deps
```

#### `backend/requirements.txt`

```text
fastapi[all]>=0.95.0
uvicorn[standard]>=0.23.0
python-can>=4.2.0
moteus>=0.3.87
asyncqt>=0.3.0
pyelftools>=0.33.0
# note: install moteus-gui with --no-deps to use system Pyside2
# pip install --no-deps moteus-gui
```

---

## Python (Frontend)

```bash
cd frontend
npm install
```

---

## Running the Application

### Backend API + WebSockets

```bash
# from project root, ensure .venv active
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

* **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **WebSocket status**: ws\://localhost:8000/ws/joint/{joint\_name}
* **WebSocket CAN log**: ws\://localhost:8000/ws/canlog

### Frontend UI

```bash
cd frontend
npm run dev
# open http://localhost:3000
```

---

## CAN (ODrive) Usage

1. **Firmware & flat\_endpoints.json**

   * Download ODrive S1 firmware: [https://docs.odriverobotics.com/releases/firmware](https://docs.odriverobotics.com/releases/firmware)
   * Extract `flat_endpoints.json` for your firmware version into `backend/configurator/config/`

2. **Configuration Restore**

```bash
# RESTores config.json settings and saves to NVM
python3 can_restore_config.py --channel can0 --node-id 0 \
  --endpoints-json ./flat_endpoints.json --config ./config.json --save-config
```

3. **Calibration**

```bash
# Runs full calibration sequence and saves to NVM
python3 can_calibrate.py --channel can0 --node-id 0 --save-config
python3 -m moteus.moteus_tool --target 1 --calibrate
```

4. **Verify CAN comms**

```bash
candump can0 -xct z -n 10
```

---

## Moteus Usage

* **USB adapter**: connect your r4.11 via `/dev/ttyACM0` (or similar)
* **MoteusBus** in backend uses the Python `moteus` package for commands
* **Install**: `pip install moteus` (core) and `pip install --no-deps moteus-gui` for GUI tools

---

## API Endpoints

| Method | Path                       | Description                       |
| ------ | -------------------------- | --------------------------------- |
| GET    | `/joints/{name}/status`    | Retrieve position & running       |
| POST   | `/joints/{name}/move`      | Move by `delta`, optional `speed` |
| POST   | `/joints/{name}/stop`      | Stop movement                     |
| POST   | `/joints/{name}/calibrate` | Run calibration sequence          |
| POST   | `/joints/{name}/configure` | Restore config.json settings      |
| POST   | `/joints/arm-all`          | Arm all joints                    |
| POST   | `/joints/disarm-all`       | Disarm all joints                 |

---

## Project Structure

```
project-root/
├── backend/
│   ├── odrive/            # ODrive CAN transport
│   ├── moteus/            # Moteus serial transport
│   ├── joints/            # Joint interface & implementations
│   ├── calibration/       # ODrive calibration helper
│   ├── configurator/      # flat_endpoints.json + config.json restore
│   ├── api/               # FastAPI routers & WS manager
│   └── main.py            # FastAPI app entrypoint
└── frontend/              # Nuxt 3 + Nuxt UI
```
