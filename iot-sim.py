import asyncio
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from aiocoap import Code, ContentFormat, Context, Message, resource
from aiocoap.error import NotFound
from aiocoap.resource import Site


class AsyncIoTResource(resource.Resource):
    """
    An observable CoAP resource that simulates sensor data with random
    values, probabilistic delays, and packet drops, including a disaster mode.
    """

    def __init__(
        self,
        temperature_range: Tuple[float, float],
        power_range: Tuple[float, float],
        drop_percentage: float,
        delay_profiles: List[Dict[str, Any]],
        coordinate: Dict[str, float],
        **kwargs: Any,
    ) -> None:
        super().__init__()

        # Initial/Normal Configuration
        self.initial_temp_min, self.initial_temp_max = temperature_range
        self.initial_power_min, self.initial_power_max = power_range
        self.initial_drop_percentage = drop_percentage
        self.initial_delay_profiles = delay_profiles

        # Current Live Configuration (changes during transition)
        self.current_temp_min, self.current_temp_max = temperature_range
        self.current_power_min, self.current_power_max = power_range
        self.current_drop_percentage = drop_percentage

        # Pre-process initial delay profiles
        self._set_delay_profiles(delay_profiles)

        # Static Configuration
        self.coordinate = coordinate

        # Disaster State Management
        self.disaster_mode: bool = False
        self.disaster_type: str = "Normal"
        self.target_config: Optional[Dict[str, Any]] = None
        self.transition_start_time: float = 0.0
        self.transition_duration: float = 0.0
        self.transition_task: Optional[asyncio.Task] = None

    def _set_delay_profiles(self, profiles: List[Dict[str, Any]]) -> None:
        """Sets up the weighted random choice for delay profiles."""
        self.delay_weights: List[int] = [p["probability"] for p in profiles]
        self.delay_ranges: List[Tuple[float, float]] = [
            (p["min"], p["max"]) for p in profiles
        ]

    def _select_delay_profile(self) -> Tuple[float, float]:
        """Selects a delay profile based on the current configured probabilities."""
        selected_range: Tuple[float, float] = random.choices(
            self.delay_ranges, weights=self.delay_weights, k=1
        )[0]
        return selected_range

    def _get_current_simulated_values(self) -> Tuple[float, float]:
        """Generates random values based on the current live configuration ranges."""
        temperature: float = random.uniform(
            self.current_temp_min, self.current_temp_max
        )
        power_consumption: float = random.uniform(
            self.current_power_min, self.current_power_max
        )
        return temperature, power_consumption

    async def _apply_gradual_transition(self) -> None:
        """Asynchronously transitions the resource behavior over the specified duration."""
        if not self.target_config:
            return

        print(
            f"\n🌪️ Starting gradual transition to {self.disaster_type} mode over {self.transition_duration}s..."
        )

        # Current starting values for the transition
        start_temp_min, start_temp_max = self.current_temp_min, self.current_temp_max
        start_power_min, start_power_max = (
            self.current_power_min,
            self.current_power_max,
        )
        start_drop_percentage = self.current_drop_percentage
        start_delay_profiles = (
            self.initial_delay_profiles
        )  # For simplicity, we only transition between initial and target profiles in the current implementation

        # Target values
        target_temp_min, target_temp_max = self.target_config["temperature_range"]
        target_power_min, target_power_max = self.target_config["power_range"]
        target_drop_percentage = self.target_config["drop_percentage"]
        target_delay_profiles = self.target_config["delay_profiles"]

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
            self.current_power_min = (
                start_power_min + (target_power_min - start_power_min) * progress
            )
            self.current_power_max = (
                start_power_max + (target_power_max - start_power_max) * progress
            )
            self.current_drop_percentage = (
                start_drop_percentage
                + (target_drop_percentage - start_drop_percentage) * progress
            )

            # For delay profiles, this implementation simply switches to the target profile after 50% transition
            # A more complex LERP could interpolate min/max values of profiles, but a simple switch is used here.
            if progress >= 0.5:
                self._set_delay_profiles(target_delay_profiles)
            else:
                self._set_delay_profiles(start_delay_profiles)

            # Print status update every 5 seconds (or adjust frequency as needed)
            if int(elapsed) % 5 == 0 and int(elapsed) == elapsed:
                print(
                    f"   [Transition Progress: {progress*100:.0f}%] Temp Range: {self.current_temp_min:.1f}-{self.current_temp_max:.1f}, Drop Rate: {self.current_drop_percentage:.1f}%"
                )

            await asyncio.sleep(1)  # Check and update every second

        # Ensure final state is exactly the target state
        self.current_temp_min, self.current_temp_max = target_temp_min, target_temp_max
        self.current_power_min, self.current_power_max = (
            target_power_min,
            target_power_max,
        )
        self.current_drop_percentage = target_drop_percentage
        self._set_delay_profiles(target_delay_profiles)

        print(
            f"🌪️ Transition complete. Simulator is now in **{self.disaster_type}** mode."
        )
        self.disaster_mode = True
        self.transition_task = None

    async def render_post(self, request: Message) -> Message:
        """Handles POST request to trigger a disaster behavior change."""
        try:
            payload: Dict[str, Any] = json.loads(request.payload.decode("utf-8"))
        except json.JSONDecodeError:
            return Message(code=Code.BAD_REQUEST, payload=b"Invalid JSON payload.")

        # Required fields in the disaster configuration
        required_keys = [
            "disaster_type",
            "temperature_range",
            "power_range",
            "drop_percentage",
            "delay_profiles",
            "transition_duration_s",
        ]
        if not all(k in payload for k in required_keys):
            return Message(
                code=Code.BAD_REQUEST,
                payload=b"Missing required fields in disaster config.",
            )

        # Stop any existing transition task
        if self.transition_task:
            self.transition_task.cancel()
            print("🛑 Canceled previous transition task.")

        # Set up the new target configuration and transition parameters
        self.disaster_type = payload["disaster_type"]
        self.target_config = {
            "temperature_range": tuple(payload["temperature_range"]),
            "power_range": tuple(payload["power_range"]),
            "drop_percentage": payload["drop_percentage"],
            "delay_profiles": payload["delay_profiles"],
        }
        self.transition_duration = float(payload["transition_duration_s"])

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

    async def render_get(self, request: Message) -> Message:
        """Asynchronously handles an incoming GET request."""

        # --- 1. Drop Simulation (uses current_drop_percentage) ---
        if random.random() * 100 < self.current_drop_percentage:
            print(
                f"🚨 Dropping packet (Current Rate: {self.current_drop_percentage:.1f}%)"
            )
            await asyncio.sleep(20)
            raise NotFound("Simulated drop leads to client timeout/failure.")

        # --- 2. Probabilistic Random Delay (uses current delay profiles) ---
        min_delay, max_delay = self._select_delay_profile()
        delay = random.uniform(min_delay, max_delay)

        if delay > 0:
            print(
                f"⏳ Non-blocking delay: {delay:.2f}s (Profile: {min_delay:.2f}s - {max_delay:.2f}s)"
            )
            await asyncio.sleep(delay)

        # --- 3. Generate Random Values (uses current ranges) ---
        temperature, power_consumption = self._get_current_simulated_values()

        # --- 4. Prepare Response Payload (JSON Format) ---
        response_data: Dict[str, Any] = {
            "timestamp": time.time(),
            "status": self.disaster_type,
            "temperature": f"{temperature:.2f}",
            "power_consumption": f"{power_consumption:.2f}",
            "unit_temperature": "C",
            "unit_power": "W",
            "geo_coordinate": self.coordinate,
        }

        payload_bytes: bytes = json.dumps(response_data).encode("utf-8")

        print(f"✅ Responding with: {payload_bytes.decode('utf-8')}")

        return Message(
            code=Code.CONTENT,
            payload=payload_bytes,
            content_format=ContentFormat.JSON,
        )


## Main Server Function (unchanged)
async def main() -> None:

    # 1. Check for command line argument
    if len(sys.argv) < 2:
        print(
            "🛑 ERROR: Please provide the path to the configuration JSON file as a command line argument."
        )
        print("Usage: python simulator.py /path/to/simulator_config.json")
        return

    CONFIG_FILE: str = sys.argv[1]

    # 2. Check and Load configuration file
    if not os.path.exists(CONFIG_FILE):
        print(f"🛑 ERROR: Configuration file not found at '{CONFIG_FILE}'.")
        return

    CONFIG: Dict[str, Any]
    try:
        with open(CONFIG_FILE, "r") as f:
            CONFIG = json.load(f)
    except json.JSONDecodeError as e:
        print(f"🛑 ERROR: Failed to parse JSON file: {e}")
        return
    except Exception as e:
        print(f"🛑 ERROR: An unexpected error occurred while reading the file: {e}")
        return

    # --- Configuration Validation & Extraction ---
    DELAY_PROFILES: List[Dict[str, Any]] = CONFIG.get("delay_profiles", [])
    COORDINATE: Optional[Dict[str, float]] = CONFIG.get("coordinate")

    if not DELAY_PROFILES:
        print("🛑 ERROR: 'delay_profiles' is missing or empty in the config file.")
        return

    if not COORDINATE or "latitude" not in COORDINATE or "longitude" not in COORDINATE:
        print(
            "🛑 ERROR: 'coordinate' with 'latitude' and 'longitude' is missing or invalid in the config file."
        )
        return

    total_probability: float = sum(p.get("probability", 0) for p in DELAY_PROFILES)
    if total_probability != 100:
        print(
            f"🛑 ERROR: Total probability of delay profiles must equal 100. Found: {total_probability}"
        )
        return

    # Extract required server parameters
    SERVER_HOST: str = CONFIG.get("server_host", "0.0.0.0")
    SERVER_PORT: int = CONFIG.get("server_port", 5683)
    RESOURCE_PATH: List[str] = CONFIG.get("resource_path", ["device", "data"])

    # 3. Create the resource tree
    root: Site = resource.Site()
    root.add_resource(tuple(RESOURCE_PATH), AsyncIoTResource(**CONFIG))

    # 4. Correctly set up aiocoap server context
    await Context.create_server_context(root, bind=(SERVER_HOST, SERVER_PORT))

    # --- Print Confirmation ---
    print("--- Async CoAP Simulator (aiocoap) Running ---")
    print(f"Loaded config from: {CONFIG_FILE}")
    print(f"Binding: coap://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Resource Path: /{'/'.join(RESOURCE_PATH)}")
    print(
        f"Geo Coordinates: Lat {COORDINATE['latitude']}, Lon {COORDINATE['longitude']}"
    )
    print(f"Total Drop Percentage: {CONFIG['drop_percentage']}%")
    print("Delay Profiles:")
    for profile in DELAY_PROFILES:
        print(
            f"  - {profile['probability']}% chance for {profile['min']:.2f}s - {profile['max']:.2f}s delay"
        )
    print("-------------------------------------------\n")

    # 5. Run forever
    await asyncio.get_event_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Async CoAP Server Shutting Down...")
