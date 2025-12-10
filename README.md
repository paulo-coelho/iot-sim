# IoT Simulator

This project is an IoT Simulator designed to mimic the behavior of various IoT devices for testing and development purposes.
It allows users to simulate data generation, device communication, and interaction with cloud services.

## Main features

- IoT devices implemented as CoAP servers
- Configurable behavior via JSON files (see examples in `scenarios/` folder)
  - Temperature values
  - Battery levels
  - Network latency
  - Drop rates
  - Coordinates
- Simulation of atypical behaviors or any event that changes the initial values (see `scenarios/event-model.json`)
  - Events can be transient or permanent
  - Received by device via CoAP POST requests

## TODO

- Orchestration of multiple devices:
  - Start/stop multiple device simulations
  - Manage sequence of events across devices
  - Aggregate data from multiple devices (MQTT?)

## Requirements

- Python 3.12+
- uv

## Usage

- Install `uv`:

  ```bash
  # with pip
  pip install uv

  # with homebrew (macOS)
  brew install uv
  ```

- Create and activate a virtual environment:

  ```bash
  uv venv --python 3.12
  uv pip install .
  ```

- Run the simulator with a scenario file:

  ```bash
  uv run iot-sim scenarios/device-model.json
  ```

- Run the client to interact with the simulated device:

  ```bash
  # GET request - fetch device data
  uv run iot-client coap://127.0.0.1:5001/device/data
  # POST request - send an event to the device
  uv run iot-client coap://127.0.0.1:5001/device/data scenarios/event-transient.json
  ```

## Scripts

The following scripts are available in the `scripts/` folder (run from the project root folder):

- `run-iot.sh`: Run the IoT simulator with from a specific folder.
  Files must follow a naming convention.
  See `scenarios/2x50/` for an example.

  ```bash
  # Usage: scripts/run-iot.sh <folder> <region> <device_id>
  ./scripts/run-iot.sh scenarios/2x50 1 1
  ```
