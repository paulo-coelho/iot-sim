import asyncio
import json
import os
import sys
import time
from typing import Any  # List and Dict are no longer imported

import aiocoap

# Define the type for the protocol context
CoAPProtocol = aiocoap.Context


# Using lowercase list and dict for generic type hints (Python 3.9+)
def load_json_file(file_path: str) -> list[dict[str, Any]] | dict[str, Any] | None:
    """Helper function to load and parse a JSON file."""
    if not os.path.exists(file_path):
        print(f"🛑 ERROR: Configuration file not found at '{file_path}'.")
        return None
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"🛑 ERROR: Failed to parse JSON file '{file_path}': {e}")
        return None
    except Exception as e:
        print(
            f"🛑 ERROR: An unexpected error occurred while reading '{file_path}': {e}"
        )
        return None


async def send_disaster_post(
    protocol: CoAPProtocol,
    device: dict[str, Any],  # Updated to use dict
    disaster_payload: dict[str, Any],  # Updated to use dict
) -> None:
    """Sends a CoAP POST request with the disaster configuration to a single device."""
    address = device.get("address")
    device_id = device.get("id")

    # The simulator expects the payload as raw bytes
    post_payload = json.dumps(disaster_payload).encode("utf-8")

    print(
        f"[{time.strftime('%H:%M:%S')}] ➡️ Sending POST to Device {device_id} at {address}..."
    )

    request = aiocoap.Message(
        code=aiocoap.Code.POST,
        uri=address,
        payload=post_payload,
        content_format=aiocoap.ContentFormat.JSON,
    )

    try:
        start_time = asyncio.get_event_loop().time()
        response = await protocol.request(request).response
        end_time = asyncio.get_event_loop().time()

        print(
            f"[{time.strftime('%H:%M:%S')}] ✅ Device {device_id} acknowledged disaster trigger."
        )
        print(f"   Response Code: {response.code}, Time: {end_time - start_time:.2f}s")
        # Optional: Print response payload if needed
        # print(f"   Response Payload: {response.payload.decode('utf-8')}")

    except Exception as e:
        print(
            f"[{time.strftime('%H:%M:%S')}] ❌ Device {device_id} failed to respond (Error: {e.__class__.__name__})."
        )


async def main() -> None:
    """
    Main orchestration logic to schedule and send disaster POST requests.
    Expects 3 arguments: devices_list.json, disaster_config.json, disaster_plan.json
    """
    if len(sys.argv) != 4:
        print("🛑 ERROR: Incorrect number of arguments.")
        print(
            "Usage: uv run orchestrator.py <devices_list.json> <disaster_config.json> <disaster_plan.json>"
        )
        sys.exit(1)

    devices_file, disaster_file, plan_file = sys.argv[1], sys.argv[2], sys.argv[3]

    devices_list = load_json_file(devices_file)
    disaster_config = load_json_file(disaster_file)
    disaster_plan = load_json_file(plan_file)

    if not all([devices_list, disaster_config, disaster_plan]):
        return

    if not isinstance(devices_list, list):
        print("🛑 ERROR: Devices file root must be a list.")
        return

    coap_devices = [d for d in devices_list if d.get("protocol") == "coap"]

    if not coap_devices:
        print("⚠️ Warning: No CoAP devices found in the device list. Exiting.")
        return

    device_map = {device["id"]: device for device in coap_devices}

    protocol = await aiocoap.Context.create_client_context()

    print(f"--- Orchestrator Ready ---")
    print(f"Total CoAP Devices: {len(coap_devices)}")
    print(f"Disaster Plan: {disaster_plan.get('name', 'N/A')}")
    print(f"Starting execution in 1 second...")
    print("--------------------------")

    # 4. Schedule and Execute the Plan
    try:
        # Sort steps by delay_s to ensure chronological execution
        steps = sorted(
            disaster_plan.get("steps", []), key=lambda x: x.get("delay_s", 0)
        )

        last_delay = 0

        for step in steps:
            target_id = step.get("target_id")
            delay_s = step.get("delay_s", 0)

            if target_id not in device_map:
                print(
                    f"Skipping Step: Device ID {target_id} not found or is not a CoAP device."
                )
                continue

            device = device_map[target_id]

            # Calculate actual sleep time (incremental delay)
            sleep_time = delay_s - last_delay
            if sleep_time > 0:
                print(f"--- Pausing for {sleep_time:.1f} seconds ---")
                await asyncio.sleep(sleep_time)

            last_delay = delay_s

            # Send the request without blocking the orchestrator
            # The result is not awaited, allowing parallel execution
            asyncio.create_task(send_disaster_post(protocol, device, disaster_config))

        print(f"\n--- All {len(steps)} disaster triggers scheduled ---")
        # Wait for all scheduled tasks to complete before shutting down the context
        await asyncio.sleep(5)  # Give some time for final messages to be processed

    except Exception as e:
        print(f"An unexpected error occurred during orchestration: {e}")
    finally:
        await protocol.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Orchestrator Shutting Down...")
