import asyncio
import json
import os
import sys

import aiocoap

# Define the type for the protocol context
CoAPProtocol = aiocoap.Context


async def send_request(
    protocol: CoAPProtocol, code: aiocoap.Code, uri: str, payload: bytes = b""
) -> None:
    """
    Helper function to create, send, and process a CoAP request.
    """
    request = aiocoap.Message(
        code=code, uri=uri, payload=payload, content_format=aiocoap.ContentFormat.JSON
    )

    print(f"--- CoAP Client Sending {code.name} to: {uri} ---")

    try:
        # Send the request and wait for the response
        start_time = asyncio.get_event_loop().time()

        # .response waits for the server reply
        response = await protocol.request(request).response

        end_time = asyncio.get_event_loop().time()

        # Output the result
        print(f"✅ Response Received ({code.name} successful)")
        print("------------------------------------------")
        print(f"Endpoint: {uri}")
        print(f"Time taken: {end_time - start_time:.3f} seconds")
        print(f"Reply Code: {response.code}")

        # Try to pretty-print JSON payload if possible
        try:
            parsed_payload = json.loads(response.payload.decode("utf-8"))
            print(f"Payload:\n{json.dumps(parsed_payload, indent=4)}")
        except json.JSONDecodeError:
            print(f"Payload (Text):\n{response.payload.decode('utf-8')}")

        print("------------------------------------------")

    except Exception as e:
        # This catches errors like timeouts, network issues, or internal server errors
        print("❌ Failed to receive response after timeout or network error.")
        print(f"Error details: {e.__class__.__name__}: {e}")


async def main() -> None:
    """
    Runs a CoAP request (GET or POST) to an endpoint provided as a
    command-line argument.
    """
    # 1. Check for command line arguments
    if len(sys.argv) < 2:
        print("🛑 ERROR: Please provide the CoAP endpoint as the first argument.")
        print("Usage (GET): uv run coap_client.py <endpoint>")
        print(
            "Usage (POST): uv run coap_client.py <endpoint> <path/to/disaster_config.json>"
        )
        sys.exit(1)

    endpoint = sys.argv[1]
    # Use str | None for the optional string type hint
    disaster_file_path: str | None = sys.argv[2] if len(sys.argv) > 2 else None

    # 2. Initialize the CoAP client context
    protocol = await aiocoap.Context.create_client_context()

    try:
        if disaster_file_path:
            # --- POST Request Logic (Disaster Trigger) ---
            if not os.path.exists(disaster_file_path):
                print(
                    f"🛑 ERROR: Disaster configuration file not found at '{disaster_file_path}'."
                )
                return

            try:
                with open(disaster_file_path, "r") as f:
                    disaster_config = json.load(f)

                # Encode the JSON payload
                post_payload = json.dumps(disaster_config).encode("utf-8")

                # Send the POST request
                await send_request(protocol, aiocoap.Code.POST, endpoint, post_payload)

            except json.JSONDecodeError as e:
                print(f"🛑 ERROR: Failed to parse JSON file: {e}")
                return

        else:
            # --- GET Request Logic (Data Retrieval) ---
            # Send the GET request
            await send_request(protocol, aiocoap.Code.GET, endpoint)

    finally:
        # 3. Clean up the client context
        await protocol.shutdown()


if __name__ == "__main__":
    # Wrap the main coroutine in asyncio.run()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Client Shutting Down...")
