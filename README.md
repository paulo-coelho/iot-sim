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
- Simulation of atypical behaviors ("disasters") (see `scenarios/disaster-model.json`)
  - Received by device via CoAP POST requests
- Orchestration of multiple devices (early development stage)

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
  uv pip install
  ```

- Run the simulator with a scenario file:

  ```bash
  uv run iot-sim.py scenarios/device-model.json
  ```

- Run the client to interact with the simulated device:
  ```bash
  uv run coap-client.py coap://127.0.0.1:5001/device/data
  ```
