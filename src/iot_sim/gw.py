import argparse
import asyncio
import csv
import json
import os
import random
import sys
from datetime import datetime
import time
from typing import Any

import aiocoap
from aiocoap import Code
from aiocoap import Context as CoAPContext

from .model import CoAPReply
from .mqtt import AsyncMQTTClient


async def send_coap_get(
    protocol: CoAPContext, uri: str, timeout: float | None = None
) -> str | None:
    request = aiocoap.Message(code=Code.GET, uri=uri)
    try:
        if timeout is not None:
            response = await asyncio.wait_for(
                protocol.request(request).response, timeout=timeout
            )
        else:
            response = await protocol.request(request).response
        if response.code == Code.NOT_FOUND:
            print(f"[CoAP] 404 Not Found for {uri}")
            return None
        return response.payload.decode("utf-8")
    except asyncio.TimeoutError:
        print(f"[CoAP] Timeout requesting {uri} (>{timeout:.2f}s)")
        return None
    except Exception as e:
        print(f"[CoAP] Error requesting {uri}: {e}")
        return None


def log_device_data(
    csv_filepath: str, data: dict[str, Any], write_header: bool = False
) -> None:
    os.makedirs(os.path.dirname(csv_filepath), exist_ok=True)
    fieldnames = [
        "timestamp",
        "uri",
        "uuid",
        "longitude",
        "latitude",
        "temperature",
        "battery",
        "error",
    ]
    file_exists = os.path.isfile(csv_filepath)
    with open(csv_filepath, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header or not file_exists:
            writer.writeheader()
        writer.writerow(data)


async def periodic_request_and_publish(
    protocol: CoAPContext,
    mqtt_client: AsyncMQTTClient,
    uri: str,
    topic: str,
    interval_ms: int,
    csv_filepath: str,
    initial_delay: float = 0.0,
    write_header: bool = False,
) -> None:
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    timeout = max((interval_ms / 1000) * 0.9, 0.5)
    reply: CoAPReply | None = None

    while True:
        start_time = asyncio.get_event_loop().time()
        payload = await send_coap_get(protocol, uri, timeout=timeout)

        error = 0
        if payload is not None:
            reply = CoAPReply.from_json(payload)
        else:
            if reply is not None:
                reply.status = (
                    "ERROR: timeout or empty payload. Battery and temperature set to 0"
                )
                reply.timestamp = asyncio.get_event_loop().time()
                reply.temperature = 0.0
                reply.battery = 0.0
                error = 1

        if reply is not None:
            # Log to CSV
            coordinate = getattr(reply, "coordinate", {})
            longitude = coordinate.get("longitude", 0)
            latitude = coordinate.get("latitude", 0)
            log_data = {
                "timestamp": reply.timestamp
                if hasattr(reply, "timestamp")
                else time.time(),
                "uri": uri,
                "uuid": getattr(reply, "uuid", ""),
                "longitude": longitude,
                "latitude": latitude,
                "temperature": getattr(reply, "temperature", ""),
                "battery": getattr(reply, "battery", ""),
                "error": error,
            }
            log_device_data(csv_filepath, log_data, write_header)
            write_header = False  # Only write header once

            async def publish_task():
                try:
                    await mqtt_client.publish(topic, reply.model_dump_json())
                except Exception as e:
                    print(f"[MQTT] Error publishing payload from {uri}: {e}")

            asyncio.create_task(publish_task())
        elapsed = asyncio.get_event_loop().time() - start_time
        sleep_time = (interval_ms / 1000) - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="IoT Gateway: Periodic CoAP to MQTT bridge"
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        required=True,
        help="Interval between requests in milliseconds",
    )
    parser.add_argument(
        "-d",
        "--devices",
        type=str,
        required=True,
        help="Path to JSON file with device addresses",
    )
    parser.add_argument(
        "-b",
        "--broker",
        type=str,
        default="localhost:1883",
        help="MQTT broker address (default: localhost:1883)",
    )
    parser.add_argument(
        "-t", "--topic", type=str, required=True, help="MQTT topic to publish to"
    )
    args = parser.parse_args()

    # Prepare logs directory and CSV filename
    os.makedirs("logs", exist_ok=True)
    csv_filename = f"logs/gw-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"

    # Load device list
    try:
        with open(args.devices, "r") as f:
            devices_json: dict[str, list[str]] = json.load(f)
            devices: list[str] = devices_json.get("devices", [])
            if not devices:
                print("[ERROR] Device list is empty or invalid in JSON file.")
                sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load devices file: {e}")
        sys.exit(1)

    async with AsyncMQTTClient(args.broker) as mqtt_client:
        protocol: CoAPContext = await CoAPContext.create_client_context()

        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(
                periodic_request_and_publish(
                    protocol,
                    mqtt_client,
                    uri,
                    args.topic,
                    args.interval,
                    csv_filename,
                    random.uniform(0, args.interval / 1000),
                    write_header=(i == 0),
                )
            )
            for i, uri in enumerate(devices)
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("[INFO] Cancelled by user.")
        finally:
            await protocol.shutdown()


def run() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGateway Shutting Down...")
