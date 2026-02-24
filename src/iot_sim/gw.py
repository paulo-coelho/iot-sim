import argparse
import asyncio
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from typing import Any

import aiocoap
from aiocoap import Code
from aiocoap import Context as CoAPContext

from .model import CoAPReply
from .mqtt import AsyncMQTTClient

CSV_FLUSH_INTERVAL = 30  # seconds


class AsyncCSVLogger:
    """
    Asynchronous CSV logger for logging data from IoT devices.
    """

    def __init__(
        self, csv_filepath: str, fieldnames: list[str], write_header: bool = False
    ):
        self.csv_filepath = csv_filepath
        self.fieldnames = fieldnames
        self.write_header = write_header
        self.queue = asyncio.Queue()
        self.csvfile = None
        self.writer = None
        self.header_written = False
        os.makedirs(os.path.dirname(csv_filepath), exist_ok=True)

    async def start(self):
        """
        Start the CSV logger. Periodically flushes the queue to disk.
        """
        self.csvfile = open(self.csv_filepath, mode="a", newline="")
        self.writer = csv.DictWriter(
            self.csvfile, fieldnames=self.fieldnames, delimiter=";"
        )
        if self.write_header or not os.path.isfile(self.csv_filepath):
            self.writer.writeheader()
            self.header_written = True
        while True:
            try:
                await self._flush_periodically()
            except asyncio.CancelledError:
                await self._flush_all()
                self.csvfile.close()
                break

    async def _flush_periodically(self):
        """
        Flush the queue to disk at regular intervals.
        """
        while True:
            await asyncio.sleep(CSV_FLUSH_INTERVAL)
            await self._flush_all()

    async def _flush_all(self):
        """
        Flush all items in the queue to disk.
        """
        while not self.queue.empty():
            data = await self.queue.get()
            self.writer.writerow(data)
            self.queue.task_done()

    async def log(self, data: dict[str, Any]):
        """
        Add a log entry to the queue.
        """
        await self.queue.put(data)


async def send_coap_get(
    protocol: CoAPContext, uri: str, timeout: float | None = None
) -> str | None:
    """
    Send a CoAP GET request and return the response payload as a string.
    """
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


async def periodic_request_and_publish(
    protocol: CoAPContext,
    mqtt_client: AsyncMQTTClient,
    uri: str,
    topic: str,
    interval_ms: int,
    csv_logger: AsyncCSVLogger,
    initial_delay: float = 0.0,
) -> None:
    """
    Periodically send CoAP GET requests, log results, and publish to MQTT.
    """
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    timeout = max((interval_ms / 1000) * 0.9, 0.5)
    reply: CoAPReply | None = None
    message_id = 1

    while True:
        start_time = asyncio.get_running_loop().time()
        sent_time = time.time_ns()
        receipt_time = -1
        error = 0

        payload = await send_coap_get(protocol, uri, timeout=timeout)

        if payload is not None:
            receipt_time = time.time_ns()
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
            coordinate = getattr(reply, "coordinate", {})
            longitude = coordinate.get("longitude", 0)
            latitude = coordinate.get("latitude", 0)
            log_data = {
                "uuid": getattr(reply, "uuid", ""),
                "message_id": message_id,
                "sent_time": sent_time,
                "receipt_time": receipt_time,
                "timestamp": getattr(reply, "timestamp", time.time()),
                "uri": uri,
                "longitude": longitude,
                "latitude": latitude,
                "temperature": getattr(reply, "temperature", ""),
                "battery": getattr(reply, "battery", ""),
                "error": error,
            }
            await csv_logger.log(log_data)
            message_id += 1

            async def publish_task():
                try:
                    await mqtt_client.publish(topic, reply.model_dump_json())
                except Exception as e:
                    print(f"[MQTT] Error publishing payload from {uri}: {e}")

            asyncio.create_task(publish_task())
        elapsed = asyncio.get_running_loop().time() - start_time
        sleep_time = (interval_ms / 1000) - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def main() -> None:
    """
    Main entry point for the IoT Gateway.
    """
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

    # CSV logger setup
    fieldnames = [
        "uuid",
        "message_id",
        "sent_time",
        "receipt_time",
        "timestamp",
        "uri",
        "longitude",
        "latitude",
        "temperature",
        "battery",
        "error",
    ]
    csv_logger = AsyncCSVLogger(csv_filename, fieldnames, write_header=True)
    csv_logger_task = asyncio.create_task(csv_logger.start())

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
                    csv_logger,
                    random.uniform(0, args.interval / 1000),
                )
            )
            for uri in devices
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("[INFO] Cancelled by user.")
        finally:
            csv_logger_task.cancel()
            await csv_logger_task
            await protocol.shutdown()


def run() -> None:
    """
    Run the IoT Gateway application.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGateway Shutting Down...")
