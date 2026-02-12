import asyncio
import json
import logging
import random
import time
from typing import Any

from aiocoap import Code, ContentFormat, Message, resource
from aiocoap.error import NotFound

from .model import DeviceConfig, EventConfig, CoAPReply


class AsyncIoTResource(resource.Resource):
    """
    An observable CoAP resource that simulates sensor data with random
    values, probabilistic delays, and packet drops, including an event trigger
    mechanism to simulate disaster, mobility and general condition changes.
    """

    def __init__(self, device_config: DeviceConfig) -> None:
        super().__init__()
        global logger
        logger = logging.getLogger("iot-sim")

        # Store the config object
        self.device_config: DeviceConfig = device_config

        # Current config
        self.current_temp_min: float
        self.current_temp_max: float
        self.current_temp_min, self.current_temp_max = device_config.temperature_range

        self.current_drop_percentage: float = device_config.drop_percentage
        self.current_battery_charge: float = device_config.battery_charge
        self.current_battery_transmit_discharge: float = (
            device_config.battery_transmit_discharge
        )
        self.current_battery_idle_discharge: float = (
            device_config.battery_idle_discharge
        )

        self._set_delay_profiles(device_config.delay_profiles)

        self.current_coordinate: dict[str, float] = device_config.coordinate

        # Event Management
        self.current_event: EventConfig = EventConfig.from_device_config(device_config)
        self.transition_task: asyncio.Task[None] | None = None
        self.discharged: bool = True if self.current_battery_charge <= 0 else False

        # Start background battery idle drain task
        self._battery_idle_drain_task_handle: asyncio.Task[None] = asyncio.create_task(
            self._battery_idle_drain_task()
        )

    async def _battery_idle_drain_task(self) -> None:
        """Background task to drain battery by idle discharge every minute."""
        while self.current_battery_charge > 0:
            await asyncio.sleep(60)
            self.current_battery_charge -= self.device_config.battery_idle_discharge
            if self.current_battery_charge <= 0:
                self.current_battery_charge = 0
                self.discharged = True
                logger.info("🔋 Battery fully discharged by idle drain.")
            else:
                logger.info(
                    f"🔋 Battery idle drain: charge now is {self.current_battery_charge:.2f}"
                )

    def _set_delay_profiles(self, profiles: list[dict[str, int | float]]) -> None:
        """Sets up the weighted random choice for delay profiles."""
        self.delay_weights: list[int | float] = [p["probability"] for p in profiles]
        self.delay_ranges: list[tuple[float, float]] = [
            (p["min"], p["max"]) for p in profiles
        ]

    def _select_delay_profile(self) -> tuple[float, float]:
        """Selects a delay profile based on the current configured probabilities."""
        selected_range: tuple[float, float] = random.choices(
            self.delay_ranges, weights=self.delay_weights, k=1
        )[0]
        return selected_range

    def _get_current_simulated_values(self) -> float:
        """Generates values based on the current live configuration ranges."""
        temperature: float = random.uniform(
            self.current_temp_min, self.current_temp_max
        )
        return temperature

    def _discharge_battery(self, value: float) -> None:
        """Discharges the battery based on current activity."""
        self.current_battery_charge -= value
        if self.current_battery_charge <= 0:
            self.current_battery_charge = 0
            self.discharged = True

    async def _apply_gradual_transition(self, transition_duration_s: float) -> None:
        """Asynchronously transitions the resource behavior over the specified duration."""

        logger.info(
            f"\n🌪️ Starting gradual transition to {self.target_event.event_name} mode over {transition_duration_s}s..."
        )

        # Current starting values for the transition
        start_temp_min, start_temp_max = self.current_temp_min, self.current_temp_max
        start_battery_transmit_discharge, start_battery_idle_discharge = (
            self.current_battery_transmit_discharge,
            self.current_battery_idle_discharge,
        )
        start_drop_percentage = self.current_drop_percentage
        start_coordinate = self.current_coordinate

        # Target values

        target_temp_min, target_temp_max = (
            self.target_event.temperature_range
            if self.target_event.temperature_range is not None
            else [self.current_temp_min, self.current_temp_max]
        )
        target_drop_percentage = (
            self.target_event.drop_percentage
            if self.target_event.drop_percentage is not None
            else self.current_drop_percentage
        )
        target_delay_profiles = (
            self.target_event.delay_profiles
            if len(self.target_event.delay_profiles) > 0
            else self.current_event.delay_profiles
        )
        target_battery_transmit_discharge = (
            self.target_event.battery_transmit_discharge
            if self.target_event.battery_transmit_discharge is not None
            else self.current_battery_transmit_discharge
        )
        target_battery_idle_discharge = (
            self.target_event.battery_idle_discharge
            if self.target_event.battery_idle_discharge is not None
            else self.current_battery_idle_discharge
        )
        target_coordinate = (
            self.target_event.coordinate
            if len(self.target_event.coordinate) > 0
            else self.current_coordinate
        )

        start_time = time.time()

        while time.time() - start_time < transition_duration_s:
            elapsed = time.time() - start_time
            # Calculate the proportion (0.0 to 1.0) of the transition completed
            progress = min(1.0, elapsed / transition_duration_s)

            # Linear interpolation (LERP) for ranges and drop rate
            # current = start + (target - start) * progress
            self.current_temp_min = (
                start_temp_min + (target_temp_min - start_temp_min) * progress
            )
            self.current_temp_max = (
                start_temp_max + (target_temp_max - start_temp_max) * progress
            )
            self.current_drop_percentage = (
                start_drop_percentage
                + (target_drop_percentage - start_drop_percentage) * progress
            )
            self.current_battery_transmit_discharge = (
                start_battery_transmit_discharge
                + (target_battery_transmit_discharge - start_battery_transmit_discharge)
                * progress
            )
            self.current_battery_idle_discharge = (
                start_battery_idle_discharge
                + (target_battery_idle_discharge - start_battery_idle_discharge)
                * progress
            )
            self.current_coordinate = {
                "latitude": start_coordinate["latitude"]
                + (target_coordinate["latitude"] - start_coordinate["latitude"])
                * progress,
                "longitude": start_coordinate["longitude"]
                + (target_coordinate["longitude"] - start_coordinate["longitude"])
                * progress,
            }

            # For delay profiles, this implementation simply switches to the target profile after 50% transition
            # A more complex LERP could interpolate min/max values of profiles, but a simple switch is used here.
            if progress >= 0.5:
                self._set_delay_profiles(target_delay_profiles)

            # Print status update every 10 seconds (or adjust frequency as needed)
            if int(elapsed) % 10 == 0:
                logger.debug(f"  [Transition Progress: {progress * 100:.0f}%]")
                logger.debug(
                    f"    Temp Range: {self.current_temp_min:.1f}-{self.current_temp_max:.1f}"
                )
                logger.debug(f"    Drop Rate: {self.current_drop_percentage:.1f}%")
                logger.debug(
                    f"    Battery Transmit Discharge: {self.current_battery_transmit_discharge:.2f}"
                )
                logger.debug(
                    f"    Battery Idle Discharge: {self.current_battery_idle_discharge:.2f}"
                )
                logger.debug(
                    f"   Geo Coordinates: Lat {self.current_coordinate['latitude']:.4f}, Lon {self.current_coordinate['longitude']:.4f}"
                )

            await asyncio.sleep(1)  # Check and update every second

        # Ensure final state is exactly the target state
        self.current_event = self.target_event
        self.current_temp_min, self.current_temp_max = target_temp_min, target_temp_max
        self.current_battery_transmit_discharge, self.current_battery_idle_discharge = (
            target_battery_transmit_discharge,
            target_battery_idle_discharge,
        )
        self.current_drop_percentage = target_drop_percentage
        self.current_coordinate = target_coordinate
        self._set_delay_profiles(target_delay_profiles)

        logger.info(
            f"🌪️ Transition complete. Simulator is now in **{self.current_event.event_name}** mode."
        )
        self.transition_task = None

    async def render_post(self, request: Message) -> Message:
        """Handles POST request to trigger a disaster behavior change."""
        # Error if battery is discharged
        if self.discharged:
            raise NotFound("Battery discharged. Device cannot process requests.")

        self._discharge_battery(self.current_battery_transmit_discharge)

        # get payload
        try:
            payload: dict[str, Any] = json.loads(request.payload.decode("utf-8"))
        except json.JSONDecodeError:
            return Message(code=Code.BAD_REQUEST, payload=b"Invalid JSON payload.")

        ## Validate Disaster Config
        try:
            self.target_event: EventConfig = EventConfig.from_incomplete_dict(
                payload, self.current_event
            )
            logger.info(f"\n🚨 Received Event Mode Trigger: {self.target_event}")
        except Exception as e:
            return Message(
                code=Code.BAD_REQUEST,
                payload=f"Event Config validation error: {e}".encode("utf-8"),
            )

        # Stop any existing transition task
        if self.transition_task:
            self.transition_task.cancel()
            logger.warning("🛑 Canceled previous transition task.")

        loop = asyncio.get_event_loop()
        if self.target_event.event_type == "transient":
            self.transition_task = loop.create_task(self._transient_event_sequence())
        else:
            self.transition_task = loop.create_task(
                self._apply_gradual_transition(self.target_event.transition_duration_s)
            )

        response_payload = {
            "status": "Event triggered",
            "event": self.target_event.event_name,
            "transition": f"{self.target_event.transition_duration_s} seconds",
            "event_type": self.target_event.event_type,
        }

        return Message(
            code=Code.CREATED,
            payload=json.dumps(response_payload).encode("utf-8"),
            content_format=ContentFormat.JSON,
        )

    async def _transient_event_sequence(self):
        self.previous_event = self.current_event
        # Transition to event config
        await self._apply_gradual_transition(self.target_event.transition_duration_s)
        logger.info(
            f"⏳ Transient event active for {self.target_event.transient_event_duration_s} seconds..."
        )
        await asyncio.sleep(self.current_event.transient_event_duration_s)
        # Transition back to previous config
        # Coordinates are never transient
        self.previous_event.coordinate = self.current_coordinate
        if self.previous_event:
            logger.info(
                f"🔄 Returning to previous event over {self.current_event.transient_event_return_s} seconds..."
            )
            self.previous_event, self.target_event = None, self.previous_event
            await self._apply_gradual_transition(
                self.current_event.transient_event_return_s
            )
        self.transition_task = None

    async def render_get(self, _request: Message) -> Message:
        """Asynchronously handles an incoming GET request."""
        # Error if battery is discharged
        if self.discharged:
            raise NotFound("Battery discharged. Device cannot process requests.")

        # Drop Simulation
        if random.random() * 100 < self.current_drop_percentage:
            logger.debug(
                f"🚨 Dropping packet (Current Rate: {self.current_drop_percentage:.1f}%)"
            )
            await asyncio.sleep(20)
            raise NotFound("Simulated drop leads to client timeout/failure.")

        # Battery discharge on each request
        self._discharge_battery(self.current_battery_transmit_discharge)

        # Probabilistic Random Delay
        min_delay, max_delay = self._select_delay_profile()
        delay = random.uniform(min_delay, max_delay)

        if delay > 0:
            logger.debug(
                f"⏳ Non-blocking delay: {delay:.2f}s (Profile: {min_delay:.2f}s - {max_delay:.2f}s)"
            )
            await asyncio.sleep(delay)

        # Generate Random Values
        temperature = self._get_current_simulated_values()

        # Prepare Response Payload
        response_data: CoAPReply = CoAPReply(
            uuid=self.device_config.uuid,
            timestamp=time.time(),
            status=self.current_event.event_name,
            temperature=temperature,
            battery=self.current_battery_charge,
            coordinate=self.current_coordinate,
        )

        payload_bytes: bytes = response_data.model_dump_json().encode("utf-8")

        logger.debug(f"✅ Responding with: {payload_bytes.decode('utf-8')}")

        return Message(
            code=Code.CONTENT,
            payload=payload_bytes,
            content_format=ContentFormat.JSON,
        )
