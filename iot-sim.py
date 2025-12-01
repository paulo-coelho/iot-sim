import asyncio
import json
import os
import random
import sys
import time
import logging
import logging.config
from typing import Any

from aiocoap import Code, ContentFormat, Context, Message, resource
from aiocoap.error import NotFound
from aiocoap.resource import Site

from config_models import DeviceConfig, DisasterConfig


class AsyncIoTResource(resource.Resource):
    """
    An observable CoAP resource that simulates sensor data with random
    values, probabilistic delays, and packet drops, including a disaster mode.
    """

    def __init__(self, device_config: DeviceConfig) -> None:
        super().__init__()

        # Store the config object
        self.device_config: DeviceConfig = device_config

        # Initial/Normal Configuration
        self.initial_temp_min: float
        self.initial_temp_max: float
        self.initial_temp_min, self.initial_temp_max = device_config.temperature_range

        self.initial_drop_percentage: float = device_config.drop_percentage
        self.initial_battery_charge: float = device_config.battery_charge
        self.initial_battery_transmit_discharge: float = (
            device_config.battery_transmit_discharge
        )
        self.initial_battery_idle_discharge: float = (
            device_config.battery_idle_discharge
        )
        self.initial_delay_profiles: list[dict[str, int | float]] = (
            device_config.delay_profiles
        )

        # Current Live Configuration (changes during transition)
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

        # Static Configuration
        self.coordinate: dict[str, float] = device_config.coordinate

        # Disaster State Management
        self.disaster_mode: bool = False
        self.disaster_type: str = "Normal"
        self.transition_start_time: float = 0.0
        self.transition_duration: float = 0.0
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
            self.current_battery_charge -= self.current_battery_idle_discharge
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
        self.discharged = True if self.current_battery_charge <= 0 else False

    async def _apply_gradual_transition(self) -> None:
        """Asynchronously transitions the resource behavior over the specified duration."""
        if not self.target_config:
            return

        logger.info(
            f"\n🌪️ Starting gradual transition to {self.disaster_type} mode over {self.transition_duration}s..."
        )

        # Current starting values for the transition
        start_temp_min, start_temp_max = self.current_temp_min, self.current_temp_max
        start_battery_transmit_discharge, start_battery_idle_discharge = (
            self.current_battery_transmit_discharge,
            self.current_battery_idle_discharge,
        )
        start_drop_percentage = self.current_drop_percentage
        start_delay_profiles = self.initial_delay_profiles  # For simplicity, we only transition between initial and target profiles in the current implementation

        # Target values
        target_temp_min, target_temp_max = self.target_config.temperature_range
        target_drop_percentage = self.target_config.drop_percentage
        target_delay_profiles = self.target_config.delay_profiles
        target_battery_transmit_discharge = (
            self.target_config.battery_transmit_discharge
        )
        target_battery_idle_discharge = self.target_config.battery_idle_discharge

        start_time = time.time()

        while time.time() - start_time < self.transition_duration:
            elapsed = time.time() - start_time
            # Calculate the proportion (0.0 to 1.0) of the transition completed
            progress = min(1.0, elapsed / self.transition_duration)

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

            # For delay profiles, this implementation simply switches to the target profile after 50% transition
            # A more complex LERP could interpolate min/max values of profiles, but a simple switch is used here.
            if progress >= 0.5:
                self._set_delay_profiles(target_delay_profiles)
            else:
                self._set_delay_profiles(start_delay_profiles)

            # Print status update every 10 seconds (or adjust frequency as needed)
            if int(elapsed) % 10 == 0:
                logger.debug(f"  [Transition Progress: {progress * 100:.0f}%]")
                logger.debug(
                    f" debugemp Range: {self.current_temp_min:.1f}-{self.current_temp_max:.1f}"
                )
                logger.debug(f"    Drop Rate: {self.current_drop_percentage:.1f}%")
                logger.debug(
                    f" debugattery Transmit Discharge: {self.current_battery_transmit_discharge:.2f}"
                )
                logger.debug(
                    f"    Battery Idle Discharge: {self.current_battery_idle_discharge:.2f}"
                )

            await asyncio.sleep(1)  # Check and update every second

        # Ensure final state is exactly the target state
        self.current_temp_min, self.current_temp_max = target_temp_min, target_temp_max
        self.current_battery_transmit_discharge, self.current_battery_idle_discharge = (
            target_battery_transmit_discharge,
            target_battery_idle_discharge,
        )
        self.current_drop_percentage = target_drop_percentage
        self._set_delay_profiles(target_delay_profiles)

        logger.info(
            f"🌪️ Transition complete. Simulator is now in **{self.disaster_type}** mode."
        )
        self.disaster_mode = True
        self.transition_task = None

    async def render_post(self, request: Message) -> Message:
        """Handles POST request to trigger a disaster behavior change."""
        # Error if battery is discharged
        if self.discharged:
            return Message(
                code=Code.SERVICE_UNAVAILABLE,
                payload=b"Battery discharged. Device cannot process requests.",
            )
        self._discharge_battery(self.current_battery_transmit_discharge)

        # get payload
        try:
            payload: dict[str, Any] = json.loads(request.payload.decode("utf-8"))
        except json.JSONDecodeError:
            return Message(code=Code.BAD_REQUEST, payload=b"Invalid JSON payload.")

        ## Validate Disaster Config
        try:
            self.target_config: DisasterConfig = DisasterConfig.from_dict(payload)
            logger.info(f"\n🚨 Received Disaster Mode Trigger: {self.target_config}")
        except Exception as e:
            return Message(
                code=Code.BAD_REQUEST,
                payload=f"Disaster Config validation error: {e}".encode("utf-8"),
            )

        self.disaster_type = self.target_config.disaster_type
        self.transition_duration = self.target_config.transition_duration_s

        # Stop any existing transition task
        if self.transition_task:
            self.transition_task.cancel()
            logger.warning("🛑 Canceled previous transition task.")

        # Start the asynchronous transition task
        loop = asyncio.get_event_loop()
        self.transition_task = loop.create_task(self._apply_gradual_transition())

        response_payload = {
            "status": "Disaster mode triggered",
            "disaster": self.disaster_type,
            "transition": f"{self.transition_duration} seconds",
        }

        return Message(
            code=Code.CREATED,
            payload=json.dumps(response_payload).encode("utf-8"),
            content_format=ContentFormat.JSON,
        )

    async def render_get(self, _request: Message) -> Message:
        """Asynchronously handles an incoming GET request."""
        # Error if battery is discharged
        if self.discharged:
            return Message(
                code=Code.SERVICE_UNAVAILABLE,
                payload=b"Battery discharged. Device cannot process requests.",
            )

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
        response_data: dict[str, str | float | dict[str, float]] = {
            "timestamp": time.time(),
            "status": self.disaster_type,
            "temperature": f"{temperature:.2f}",
            "battery": f"{self.current_battery_charge:.2f}",
            "geo_coordinate": self.coordinate,
        }

        payload_bytes: bytes = json.dumps(response_data).encode("utf-8")

        logger.debug(f"✅ Responding with: {payload_bytes.decode('utf-8')}")

        return Message(
            code=Code.CONTENT,
            payload=payload_bytes,
            content_format=ContentFormat.JSON,
        )


## Main Server Function (unchanged)
async def main() -> None:
    # Load logging configuration
    with open("log-config.json", "r") as f:
        log_config = json.load(f)
    # Generate timestamped log filename
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_filename = f"log-iot-sim-{timestamp}.log"
    log_config["handlers"]["file"]["filename"] = log_filename
    logging.config.dictConfig(log_config)
    global logger
    logger = logging.getLogger("iot-sim")

    if len(sys.argv) < 2:
        logger.error(
            "🛑 Please provide the path to the configuration JSON file as a command line argument."
        )
        logger.info("Usage: python iot-sim.py /path/to/simulator_config.json")
        return

    CONFIG_FILE: str = sys.argv[1]

    if not os.path.exists(CONFIG_FILE):
        logger.error(f"🛑 Configuration file not found at '{CONFIG_FILE}'.")
        return

    try:
        config = DeviceConfig.from_file(CONFIG_FILE)
    except Exception as e:
        logger.error(f"🛑 An unexpected error occurred while reading the file: {e}")
        return

    DELAY_PROFILES = config.delay_profiles
    total_probability: float = sum(p.get("probability", 0) for p in DELAY_PROFILES)
    if total_probability != 100:
        logger.error(
            f"🛑 Total probability of delay profiles must equal 100. Found: {total_probability}"
        )
        return

    # Extract required server parameters
    SERVER_HOST = config.server_host
    SERVER_PORT = config.server_port
    RESOURCE_PATH = config.resource_path

    # Create the resource tree
    root: Site = resource.Site()
    root.add_resource(tuple(RESOURCE_PATH), AsyncIoTResource(config))

    # Set up aiocoap server context
    _ = await Context.create_server_context(root, bind=(SERVER_HOST, SERVER_PORT))

    # --- Print Confirmation ---
    logger.info("--- Async CoAP Simulator (aiocoap) Running ---")
    logger.info(f"Loaded config from: {CONFIG_FILE}")
    logger.info(f"UUID: {config.uuid}")
    logger.info(f"Binding: coap://{SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"Resource Path: /{'/'.join(RESOURCE_PATH)}")
    logger.info(
        f"Geo Coordinates: Lat {config.coordinate['latitude']:.4f}, Lon {config.coordinate['longitude']:.4f}"
    )
    logger.info("Battery information:")
    logger.info(f"  Initial charge: {config.battery_charge:.2f}")
    logger.info(f"  Request discharge: {config.battery_transmit_discharge:.2f}")
    logger.info(f"  Idle discharge: {config.battery_idle_discharge:.2f}")
    logger.info(f"Total Drop Percentage: {config.drop_percentage:.2f}%")
    logger.info("Delay Profiles:")
    for profile in DELAY_PROFILES:
        logger.info(
            f"  - {profile['probability']}% chance for {profile['min']:.2f}s - {profile['max']:.2f}s delay"
        )
    logger.info("-------------------------------------------\n")
    await asyncio.get_event_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Async CoAP Server Shutting Down...")
