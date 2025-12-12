import argparse
import asyncio
import json
import random
import sys

import aiocoap
from aiocoap import Code
from aiocoap import Context as CoAPContext

from .mqtt import AsyncMQTTClient
from .model import CoAPReply


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


async def periodic_request_and_publish(
    protocol: CoAPContext,
    mqtt_client: AsyncMQTTClient,
    uri: str,
    topic: str,
    interval_ms: int,
    initial_delay: float = 0.0,
) -> None:
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    timeout = max((interval_ms / 1000) * 0.9, 0.5)
    reply: CoAPReply | None = None

    while True:
        start_time = asyncio.get_event_loop().time()
        payload = await send_coap_get(protocol, uri, timeout=timeout)

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

        if reply is not None:

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
            await protocol.shutdown()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGateway Shutting Down...")
