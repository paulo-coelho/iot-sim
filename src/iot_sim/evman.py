import asyncio
import json
import sys
from typing import Any

import aiocoap

from .model import EventConfig


TIMEOUT_POST = 5  # seconds


class DeviceEvent:
    def __init__(self, time_ms: int, device: str, event: EventConfig):
        self.time_ms = time_ms
        self.device = device
        self.event = event

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceEvent":
        try:
            return cls(
                time_ms=data["time_ms"],
                device=data["device"],
                event=EventConfig.from_dict(data["event"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            print(f"Invalid event data: {e}")
            sys.exit(1)


class EventCoordinator:
    def __init__(self, schedule: list[DeviceEvent]):
        self.schedule = sorted(schedule, key=lambda e: e.time_ms)

    async def send_event(self, device_event: DeviceEvent):
        protocol = await aiocoap.Context.create_client_context()
        payload = device_event.event.model_dump_json(exclude_none=True).encode("utf-8")
        request = aiocoap.Message(
            code=aiocoap.POST, uri=device_event.device, payload=payload
        )
        try:
            response = await asyncio.wait_for(
                protocol.request(request).response, timeout=TIMEOUT_POST
            )
            print(f"Sent event to {device_event.device}: {response.code}")
        except asyncio.TimeoutError:
            print(f"Timeout sending event to {device_event.device}")
        except Exception as e:
            print(f"Failed to send event to {device_event.device}: {e}")

    async def run(self):
        start_time = asyncio.get_event_loop().time()
        tasks = []
        for device_event in self.schedule:
            delay = (device_event.time_ms / 1000.0) - (
                asyncio.get_event_loop().time() - start_time
            )
            delay = max(0, delay)  # Ensure no negative delays
            tasks.append(asyncio.create_task(self.schedule_event(device_event, delay)))
        await asyncio.gather(*tasks)

    async def schedule_event(self, device_event: DeviceEvent, delay: float):
        await asyncio.sleep(delay)
        await self.send_event(device_event)


def load_schedule(path: str) -> list[DeviceEvent]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return [DeviceEvent.from_dict(item) for item in data]
    except FileNotFoundError:
        print(f"Schedule file not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to parse schedule JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error loading schedule: {e}")
        sys.exit(1)


async def main(schedule_path: str):
    try:
        schedule = load_schedule(schedule_path)
        coordinator = EventCoordinator(schedule)
        await coordinator.run()
    except Exception as e:
        print(f"Fatal error in main: {e}")
        sys.exit(1)


def run() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        if len(sys.argv) != 2:
            print("Usage: uv ev-man <schedule.json>")
            sys.exit(1)
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        print("\nGateway Shutting Down...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
