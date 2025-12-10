import asyncio
import json
import os
import sys
import logging
import logging.config
from .model import DeviceConfig
from aiocoap import Context, resource
from aiocoap.resource import Site

from .sim import AsyncIoTResource

logger = None


async def main():
    with open("log-config.json", "r") as f:
        log_config = json.load(f)
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    if len(sys.argv) < 2:
        print("🛑 ERROR: Please provide the configuration file as the first argument.")
        print("Usage: uv run iot-sim <configuration file>")
        sys.exit(1)

    CONFIG_FILE: str = sys.argv[1]
    if not os.path.exists(CONFIG_FILE):
        print(f"🛑 Configuration file not found at '{CONFIG_FILE}'.")
        return

    try:
        config = DeviceConfig.from_file(CONFIG_FILE)
    except Exception as e:
        print(f"🛑 An unexpected error occurred while reading the file: {e}")
        return

    # Set log filename using device UUID
    log_filename = os.path.join(logs_dir, f"dev-{config.uuid}.log")
    log_config["handlers"]["file"]["filename"] = log_filename
    logging.config.dictConfig(log_config)
    global logger
    logger = logging.getLogger("iot-sim")

    if len(sys.argv) < 2:
        print(
            "🛑 Please provide the path to the configuration JSON file as a command line argument."
        )
        print("Usage: python -m iot_sim /path/to/simulator_config.json")
        return

    DELAY_PROFILES = config.delay_profiles
    total_probability: float = sum(p.get("probability", 0) for p in DELAY_PROFILES)
    if total_probability != 100:
        logger.error(
            f"🛑 Total probability of delay profiles must equal 100. Found: {total_probability}"
        )
        return

    SERVER_HOST = config.server_host
    SERVER_PORT = config.server_port
    RESOURCE_PATH = config.resource_path

    root: Site = resource.Site()
    root.add_resource(tuple(RESOURCE_PATH), AsyncIoTResource(config))

    # Set up aiocoap server context
    _ = await Context.create_server_context(root, bind=(SERVER_HOST, SERVER_PORT))

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


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if logger:
            logger.info("\n👋 Async CoAP Server Shutting Down...")
        else:
            print("\n👋 Async CoAP Server Shutting Down...")

