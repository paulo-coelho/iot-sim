import asyncio
import json
import os
import random
import sys

from aiocoap import Code, ContentFormat, Context, Message, resource
from aiocoap.error import NotFound

# --- 1. The Async CoAP Resource ---


class AsyncIoTResource(resource.Resource):
    """
    An observable CoAP resource that simulates sensor data with random
    values, probabilistic delays, and packet drops using asyncio.
    """

    def __init__(
        self, temperature_range, power_range, drop_percentage, delay_profiles, **kwargs
    ):
        super().__init__()

        # Configuration
        self.temp_min, self.temp_max = temperature_range
        self.power_min, self.power_max = power_range
        self.drop_percentage = drop_percentage
        self.delay_profiles = delay_profiles

        # Pre-process profiles for weighted random choice
        self.delay_weights = [p["probability"] for p in delay_profiles]
        self.delay_ranges = [(p["min"], p["max"]) for p in delay_profiles]

    def _select_delay_profile(self):
        """Selects a delay profile based on the configured probabilities."""
        # perform the weighted selection
        selected_range = random.choices(
            self.delay_ranges, weights=self.delay_weights, k=1
        )[0]
        return selected_range

    async def render_get(self, request):
        """Asynchronously handles an incoming GET request."""

        # --- 1. Drop Simulation ---
        if random.random() * 100 < self.drop_percentage:
            print(f"🚨 Dropping packet (Rate: {self.drop_percentage}%)")
            # Simulate a hang/timeout for a dropped packet
            await asyncio.sleep(20)
            raise NotFound(
                "Simulated drop leads to client timeout/failure."
            )  # <-- Use the imported exception

        # --- 2. Probabilistic Random Delay (Non-blocking) ---
        min_delay, max_delay = self._select_delay_profile()
        delay = random.uniform(min_delay, max_delay)

        if delay > 0:
            print(
                f"⏳ Introducing non-blocking delay: {delay:.2f}s (Profile: {min_delay:.2f}s - {max_delay:.2f}s)"
            )
            # Use asyncio.sleep to pause execution without blocking the event loop
            await asyncio.sleep(delay)

        # --- 3. Generate Random Values ---
        temperature = random.uniform(self.temp_min, self.temp_max)
        power_consumption = random.uniform(self.power_min, self.power_max)

        # --- 4. Prepare Response Payload ---
        payload_text = f"Temp: {temperature:.2f} C | Power: {power_consumption:.2f} W"

        return Message(
            code=Code.CONTENT,
            payload=payload_text.encode("utf-8"),
            content_format=ContentFormat.TEXT,
        )


## Main Server Function
async def main():

    # 1. Check for command line argument
    if len(sys.argv) < 2:
        print(
            "🛑 ERROR: Please provide the path to the configuration JSON file as a command line argument."
        )
        print("Usage: python simulator.py /path/to/simulator_config.json")
        return

    CONFIG_FILE = sys.argv[1]

    # 2. Check and Load configuration file
    if not os.path.exists(CONFIG_FILE):
        print(f"🛑 ERROR: Configuration file not found at '{CONFIG_FILE}'.")
        return

    try:
        with open(CONFIG_FILE, "r") as f:
            CONFIG = json.load(f)
    except json.JSONDecodeError as e:
        print(f"🛑 ERROR: Failed to parse JSON file: {e}")
        return
    except Exception as e:
        print(f"🛑 ERROR: An unexpected error occurred while reading the file: {e}")
        return

    # --- Configuration Validation ---
    DELAY_PROFILES = CONFIG.get("delay_profiles", [])
    if not DELAY_PROFILES:
        print("🛑 ERROR: 'delay_profiles' is missing or empty in the config file.")
        return

    total_probability = sum(p.get("probability", 0) for p in DELAY_PROFILES)
    if total_probability != 100:
        print(
            f"🛑 ERROR: Total probability of delay profiles must equal 100. Found: {total_probability}"
        )
        return

    # Extract required server parameters
    SERVER_HOST = CONFIG.get("server_host", "0.0.0.0")
    SERVER_PORT = CONFIG.get("server_port", 5683)
    RESOURCE_PATH = tuple(CONFIG.get("resource_path", ["device", "data"]))

    # 3. Create the resource tree
    root = resource.Site()
    root.add_resource(RESOURCE_PATH, AsyncIoTResource(**CONFIG))

    # 4. Correctly set up aiocoap server context
    await Context.create_server_context(root, bind=(SERVER_HOST, SERVER_PORT))

    # --- Print Confirmation ---
    print("--- Async CoAP Simulator (aiocoap) Running ---")
    print(f"Loaded config from: {CONFIG_FILE}")
    print(f"Binding: coap://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Resource Path: /{'/'.join(RESOURCE_PATH)}")
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
