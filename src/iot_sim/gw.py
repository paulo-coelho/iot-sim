import argparse
import asyncio
import csv
import json
import os
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

MQTT_WORKER_COUNT = 10  # Number of concurrent MQTT publish workers
NET_SEMAPHORE_LIMIT = 3000  # Max concurrent CoAP requests

DEVICE_TIMEOUT = 15  # seconds


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
        self._flush_task = None

    async def start(self):
        """
        Start the CSV logger. Periodically flushes the queue to disk.
        """
        os.makedirs(os.path.dirname(self.csv_filepath), exist_ok=True)
        self.csvfile = open(self.csv_filepath, mode="a", newline="")
        self.writer = csv.DictWriter(
            self.csvfile, fieldnames=self.fieldnames, delimiter=";"
        )
        if self.write_header or not os.path.isfile(self.csv_filepath):
            self.writer.writeheader()

        self._flush_task = asyncio.create_task(self._periodic_flush_loop())

    async def _periodic_flush_loop(self):
        try:
            while True:
                await asyncio.sleep(CSV_FLUSH_INTERVAL)
                await self._flush_all()
        except asyncio.CancelledError:
            await self._flush_all()
            if self.csvfile:
                self.csvfile.close()

    async def _flush_all(self):
        while not self.queue.empty():
            data = await self.queue.get()
            if self.writer:
                self.writer.writerow(data)
            self.queue.task_done()
        if self.csvfile:
            self.csvfile.flush()

    async def log(self, data: dict[str, Any]):
        """
        Add a log entry to the queue.
        """
        await self.queue.put(data)

    async def stop(self):
        """
        Add a log entry to the queue.
        """
        if self._flush_task:
            self._flush_task.cancel()
            await self._flush_task


async def send_coap_get(
    protocol: CoAPContext, uri: str, semaphore: asyncio.Semaphore
) -> str | None:
    """
    Send a CoAP GET request and return the response payload as a string.
    """
    request = aiocoap.Message(code=Code.GET, uri=uri)

    try:
        async with semaphore:
            response = await asyncio.wait_for(
                protocol.request(request).response, timeout=DEVICE_TIMEOUT
            )
        if response.code == Code.NOT_FOUND:
            print(f"[CoAP] 404 Not Found for {uri}")
            return None
        return response.payload.decode("utf-8")
    except asyncio.TimeoutError:
        print(f"[CoAP] Timeout requesting {uri} (>{DEVICE_TIMEOUT:.2f}s)")
        return None
    except Exception as e:
        print(f"[CoAP] Error requesting {uri}: {e}")
        return None


async def periodic_request_and_publish(
    protocol: CoAPContext,
    mqtt_client: AsyncMQTTClient,
    mqtt_publish_queue: asyncio.Queue[tuple[str, str] | None],
    uri: str,
    topic: str,
    interval_ms: int,
    csv_logger: AsyncCSVLogger,
    semaphore: asyncio.Semaphore,
    initial_delay: float = 0.0,
) -> None:
    """
    Periodically send CoAP GET requests, log results, and enqueue MQTT publish requests.
    """
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)

    reply: CoAPReply | None = None
    device_lock = asyncio.Lock()
    message_id = 1

    while True:
        loop_start = time.monotonic()
        sent_time = time.time_ns()
        receipt_time = -1
        error = 0
        payload = None

        if device_lock.locked():
            error = 2  # Internal code for 'Skipped/Busy'
            print(f"[Warn] {uri} is lagging. Skipping current interval.")
        else:
            async with device_lock:
                payload = await send_coap_get(protocol, uri, semaphore)

            if payload is not None:
                receipt_time = time.time_ns()
                reply = CoAPReply.from_json(payload)
            else:
                error = 1

        if reply is not None:
            if error > 0:
                reply.status = (
                    "ERROR: Battery and temperature set to 0. See error code."
                )
                reply.temperature = 0.0
                reply.battery = 0.0

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
            if mqtt_client:
                await mqtt_publish_queue.put((topic, reply.model_dump_json()))

        message_id += 1
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0, interval_ms / 1000 - elapsed)
        await asyncio.sleep(sleep_time)


async def mqtt_publish_worker(
    mqtt_client: AsyncMQTTClient,
    mqtt_publish_queue: asyncio.Queue[tuple[str, str] | None],
):
    while True:
        item = await mqtt_publish_queue.get()
        if item is None:
            mqtt_publish_queue.task_done()
            break
        topic, payload = item
        try:
            await mqtt_client.publish(topic, payload)
        except Exception as e:
            print(f"[MQTT Worker] Failed to publish: {e}")
        mqtt_publish_queue.task_done()


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
    await csv_logger.start()

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

        # Limit concurrent network IO
        net_semaphore = asyncio.Semaphore(NET_SEMAPHORE_LIMIT)

        # MQTT publish queue and workers
        mqtt_publish_queue = asyncio.Queue()
        mqtt_workers = [
            asyncio.create_task(mqtt_publish_worker(mqtt_client, mqtt_publish_queue))
            for _ in range(MQTT_WORKER_COUNT)
        ]

        step = (args.interval / 1000) / len(devices) if devices else 0

        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(
                periodic_request_and_publish(
                    protocol,
                    mqtt_client,
                    mqtt_publish_queue,
                    uri,
                    args.topic,
                    args.interval,
                    csv_logger,
                    net_semaphore,
                    step * i,
                )
            )
            for i, uri in enumerate(devices)
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("[INFO] Cancelled by user.")
            pass
        finally:
            await csv_logger.stop()
            await protocol.shutdown()
            # Signal MQTT workers to exit
            for _ in range(MQTT_WORKER_COUNT):
                await mqtt_publish_queue.put(None)
            await asyncio.gather(*mqtt_workers)


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
