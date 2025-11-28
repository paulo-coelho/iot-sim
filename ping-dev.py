import json
import os
import random
import sys
import time

from scapy.all import ICMP, IP, send, sniff

# --- Simulation Logic Class ---


class PingResponder:
    """Handles ICMP Echo Requests and applies probabilistic delay and drop logic."""

    def __init__(self, config):
        self.drop_percentage = config["drop_percentage"]
        self.delay_profiles = config["delay_profiles"]
        self.listen_ip = config["listen_ip"]
        self.interface_name = config["interface_name"]  # <--- NEW: Read from config

        # Pre-process profiles for weighted random choice
        self.delay_weights = [p["probability"] for p in self.delay_profiles]
        self.delay_ranges = [(p["min"], p["max"]) for p in self.delay_profiles]

    def _select_delay_profile(self):
        """Selects a delay profile based on configured probabilities."""
        selected_range = random.choices(
            self.delay_ranges, weights=self.delay_weights, k=1
        )[0]
        return selected_range

    def handle_ping(self, packet):
        """
        Callback function executed by scapy when an ICMP Echo Request is received.
        """
        # Ensure it's an ICMP Echo Request (type 8) destined for our target IP
        if ICMP in packet and packet[ICMP].type == 8:

            if packet[IP].dst != self.listen_ip:
                return  # Ignore packets not for our target IP

            # --- 1. Drop Simulation ---
            if random.random() * 100 < self.drop_percentage:
                print(
                    f"🚨 Dropping ping from {packet[IP].src} (Drop Rate: {self.drop_percentage}%)"
                )
                return  # Do nothing, effectively dropping the packet

            # --- 2. Probabilistic Random Delay ---
            min_delay, max_delay = self._select_delay_profile()
            delay = random.uniform(min_delay, max_delay)

            if delay > 0:
                print(
                    f"⏳ Introducing delay: {delay:.3f}s (Profile: {min_delay:.3f}s - {max_delay:.3f}s)"
                )
                # Use time.sleep since sniffer threads are synchronous
                time.sleep(delay)

            # --- 3. Construct and Send Echo Reply (ICMP type 0) ---

            # Create the IP layer: swap source and destination
            ip_layer = IP(src=packet[IP].dst, dst=packet[IP].src)

            # Create the ICMP layer: change type from 8 (Request) to 0 (Reply)
            icmp_layer = ICMP(type=0, id=packet[ICMP].id, seq=packet[ICMP].seq)

            # Replicate the original payload (data)
            payload = bytes(packet[ICMP].payload)

            # Build and send the packet, specifying the output interface
            reply_packet = ip_layer / icmp_layer / payload

            # <--- KEY CHANGE: Use the configured interface for sending the reply --->
            send(reply_packet, iface=self.interface_name, verbose=0)

            print(f"✅ Replied to ping from {packet[IP].src} via {self.interface_name}")


def load_config(config_file):
    """Loads and validates configuration from the JSON file."""
    if not os.path.exists(config_file):
        print(f"🛑 ERROR: Configuration file not found at '{config_file}'.")
        sys.exit(1)

    try:
        with open(config_file, "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"🛑 ERROR: Failed to load configuration: {e}")
        sys.exit(1)

    # Validate essential fields
    if "interface_name" not in config:
        print(
            "🛑 ERROR: 'interface_name' must be specified in the configuration file (e.g., 'en0')."
        )
        sys.exit(1)

    # Basic Validation for probabilities
    delay_profiles = config.get("delay_profiles", [])
    total_probability = sum(p.get("probability", 0) for p in delay_profiles)
    if total_probability != 100:
        print(
            f"🛑 ERROR: Total probability of delay profiles must equal 100. Found: {total_probability}"
        )
        sys.exit(1)

    return config


def main():
    # 1. Get config file path
    if len(sys.argv) < 2:
        print("🛑 ERROR: Please provide the path to the configuration JSON file.")
        print("Usage: python ping_simulator.py /path/to/ping_config.json")
        sys.exit(1)

    config = load_config(sys.argv[1])

    # 2. Initialize and start the sniffer
    responder = PingResponder(config)

    # Filter to only capture ICMP Echo Requests destined for our specific IP
    # We use the configured interface for the BPF filter as well.
    bpf_filter = f"icmp and dst host {config['listen_ip']}"

    print("--- ICMP Ping Simulator Running ---")
    print(f"Interface: {config['interface_name']}")
    print(f"Listening on IP: {config['listen_ip']}")
    print(f"BPF Filter: {bpf_filter}")
    print(f"Drop Percentage: {config['drop_percentage']}%")
    print("Delay Profiles:")
    for profile in config["delay_profiles"]:
        # Convert seconds to milliseconds for display clarity
        print(
            f"  - {profile['probability']}% chance for {profile['min']*1000:.1f}ms - {profile['max']*1000:.1f}ms delay"
        )
    print("-----------------------------------")
    print("Press Ctrl+C to stop.")

    try:
        # Start sniffing packets on the specified interface
        sniff(
            filter=bpf_filter,
            iface=config["interface_name"],
            prn=responder.handle_ping,
            store=0,
        )
    except PermissionError:
        print("\n🛑 FATAL ERROR: Insufficient permissions to use raw sockets.")
        print(
            "Please run the script with elevated privileges (e.g., sudo/Administrator)."
        )
    except KeyboardInterrupt:
        print("\n👋 Ping Simulator Shutting Down...")
    except Exception as e:
        print(f"\n🛑 An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
