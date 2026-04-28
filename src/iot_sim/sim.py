import asyncio
import json
import logging
import random
import time
from typing import Any

from aiocoap import Code, ContentFormat, Message, resource
from aiocoap.error import ServiceUnavailable

from .model import DeviceConfig, EventConfig, CoAPReply
from .battery import BatteryModel
from .sensor import TemperatureSensor, PressureSensor, MultiSensor
from .network import NetworkModel


class AsyncIoTResource(resource.Resource):
    """
    An observable CoAP resource that simulates sensor data with modular models,
    including an event trigger mechanism to simulate disaster, mobility
    and general condition changes.
    """

    def __init__(self, device_config: DeviceConfig) -> None:
        super().__init__()
        global logger
        logger = logging.getLogger("iot-sim")

        # Store the config object
        self.device_config: DeviceConfig = device_config

        # Initialize Models
        self.battery = BatteryModel(
            initial_charge=device_config.battery_charge,
            idle_rate=device_config.battery_idle_discharge,
            transmit_rate=device_config.battery_transmit_discharge
        )
        
        self.sensor = MultiSensor({
            "temperature": TemperatureSensor(
                temp_min=device_config.temperature_range[0],
                temp_max=device_config.temperature_range[1]
            ),
            "pressure": PressureSensor(
                pressure_min=device_config.pressure_range[0],
                pressure_max=device_config.pressure_range[1]
            )
        })

        self.network = NetworkModel(
            drop_percentage=device_config.drop_percentage,
            delay_profiles=device_config.delay_profiles
        )

        self.current_coordinate: dict[str, float] = device_config.coordinate

        # Event Management
        self.current_event: EventConfig = EventConfig.from_device_config(device_config)
        self.transition_task: asyncio.Task[None] | None = None

        # Start background battery idle drain task
        self._battery_idle_drain_task_handle: asyncio.Task[None] = asyncio.create_task(
            self._battery_idle_drain_task()
        )

    async def _battery_idle_drain_task(self) -> None:
        """Background task to drain battery by idle discharge every minute."""
        while not self.battery.is_discharged:
            await asyncio.sleep(60)
            self.battery.consume_idle()
            if self.battery.is_discharged:
                logger.info("🔋 Battery fully discharged by idle drain.")
            else:
                logger.info(
                    f"🔋 Battery idle drain: charge now is {self.battery.charge:.2f}"
                )

    async def _apply_gradual_transition(self, transition_duration_s: float) -> None:
        """Asynchronously transitions the resource behavior over the specified duration."""

        logger.info(
            f"\n🌪️ Starting gradual transition to {self.target_event.event_name} mode over {transition_duration_s}s..."
        )

        # Current starting values for the transition
        start_temp_min, start_temp_max = self.sensor.sensors["temperature"].temp_min, self.sensor.sensors["temperature"].temp_max
        start_press_min, start_press_max = self.sensor.sensors["pressure"].pressure_min, self.sensor.sensors["pressure"].pressure_max
        
        start_battery_transmit_discharge, start_battery_idle_discharge = (
            self.battery.transmit_rate,
            self.battery.idle_rate,
        )
        start_drop_percentage = self.network.drop_percentage
        start_coordinate = self.current_coordinate

        # Target values
        target_temp_min, target_temp_max = (
            self.target_event.temperature_range
            if self.target_event.temperature_range is not None
            else [self.sensor.sensors["temperature"].temp_min, self.sensor.sensors["temperature"].temp_max]
        )
        target_press_min, target_press_max = (
            self.target_event.pressure_range
            if self.target_event.pressure_range is not None
            else [self.sensor.sensors["pressure"].pressure_min, self.sensor.sensors["pressure"].pressure_max]
        )

        target_drop_percentage = (
            self.target_event.drop_percentage
            if self.target_event.drop_percentage is not None
            else self.network.drop_percentage
        )
        target_delay_profiles = (
            self.target_event.delay_profiles
            if len(self.target_event.delay_profiles) > 0
            else self.network.delay_profiles
        )
        target_battery_transmit_discharge = (
            self.target_event.battery_transmit_discharge
            if self.target_event.battery_transmit_discharge is not None
            else self.battery.transmit_rate
        )
        target_battery_idle_discharge = (
            self.target_event.battery_idle_discharge
            if self.target_event.battery_idle_discharge is not None
            else self.battery.idle_rate
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
            curr_temp_min = (
                start_temp_min + (target_temp_min - start_temp_min) * progress
            )
            curr_temp_max = (
                start_temp_max + (target_temp_max - start_temp_max) * progress
            )
            
            curr_press_min = (
                start_press_min + (target_press_min - start_press_min) * progress
            )
            curr_press_max = (
                start_press_max + (target_press_max - start_press_max) * progress
            )

            self.sensor.update_parameters(
                temperature_range=(curr_temp_min, curr_temp_max),
                pressure_range=(curr_press_min, curr_press_max)
            )

            curr_drop_percentage = (
                start_drop_percentage
                + (target_drop_percentage - start_drop_percentage) * progress
            )
            self.network.update_parameters(drop_percentage=curr_drop_percentage)

            curr_battery_transmit_discharge = (
                start_battery_transmit_discharge
                + (target_battery_transmit_discharge - start_battery_transmit_discharge)
                * progress
            )
            curr_battery_idle_discharge = (
                start_battery_idle_discharge
                + (target_battery_idle_discharge - start_battery_idle_discharge)
                * progress
            )
            self.battery.update_parameters(
                idle_rate=curr_battery_idle_discharge,
                transmit_rate=curr_battery_transmit_discharge
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
            if progress >= 0.5:
                self.network.update_parameters(delay_profiles=target_delay_profiles)

            # Print status update every 10 seconds
            if int(elapsed) % 10 == 0:
                logger.debug(f"  [Transition Progress: {progress * 100:.0f}%]")
                logger.debug(
                    f"    Temp Range: {self.sensor.sensors['temperature'].temp_min:.1f}-{self.sensor.sensors['temperature'].temp_max:.1f}"
                )
                logger.debug(
                    f"    Press Range: {self.sensor.sensors['pressure'].pressure_min:.1f}-{self.sensor.sensors['pressure'].pressure_max:.1f}"
                )
                logger.debug(f"    Drop Rate: {self.network.drop_percentage:.1f}%")
                logger.debug(
                    f"    Battery Transmit Discharge: {self.battery.transmit_rate:.2f}"
                )
                logger.debug(
                    f"    Battery Idle Discharge: {self.battery.idle_rate:.2f}"
                )
                logger.debug(
                    f"   Geo Coordinates: Lat {self.current_coordinate['latitude']:.4f}, Lon {self.current_coordinate['longitude']:.4f}"
                )

            await asyncio.sleep(1)  # Check and update every second

        # Ensure final state is exactly the target state
        self.current_event = self.target_event
        self.sensor.update_parameters(
            temperature_range=(target_temp_min, target_temp_max),
            pressure_range=(target_press_min, target_press_max)
        )
        self.battery.update_parameters(
            idle_rate=target_battery_idle_discharge,
            transmit_rate=target_battery_transmit_discharge
        )
        self.network.update_parameters(
            drop_percentage=target_drop_percentage,
            delay_profiles=target_delay_profiles
        )
        self.current_coordinate = target_coordinate

        logger.info(
            f"🌪️ Transition complete. Simulator is now in **{self.current_event.event_name}** mode."
        )
        self.transition_task = None

    async def render_post(self, request: Message) -> Message:
        """Handles POST request to trigger a disaster behavior change."""
        # Error if battery is discharged
        if self.battery.is_discharged:
            raise ServiceUnavailable("Battery fully discharged.")

        self.battery.consume_transmit()

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
        if self.battery.is_discharged:
            raise ServiceUnavailable("Battery fully discharged.")

        # Drop Simulation
        if self.network.should_drop():
            logger.debug(
                f"🚨 Dropping packet (Current Rate: {self.network.drop_percentage:.1f}%)"
            )
            await asyncio.sleep(20)
            raise asyncio.CancelledError("Simulated drop")

        # Battery discharge on each request
        self.battery.consume_transmit()

        # Probabilistic Random Delay
        await self.network.apply_delay()

        # Generate Random Values
        sensor_data = self.sensor.get_reading()

        # Prepare Response Payload
        response_data: CoAPReply = CoAPReply(
            uuid=self.device_config.uuid,
            timestamp=time.time(),
            status=self.current_event.event_name,
            sensor_data=sensor_data,
            battery=self.battery.charge,
            coordinate=self.current_coordinate,
        )

        payload_bytes: bytes = response_data.model_dump_json().encode("utf-8")

        logger.debug(f"✅ Responding with: {payload_bytes.decode('utf-8')}")

        return Message(
            code=Code.CONTENT,
            payload=payload_bytes,
            content_format=ContentFormat.JSON,
        )
