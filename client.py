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
        start_time = asyncio.get_event_loop().time()
        response = await protocol.request(request).response
        end_time = asyncio.get_event_loop().time()

        if response.code == aiocoap.Code.NOT_FOUND:
            print("❌ ERROR: Resoure not found.")
        else:
            # Output the result
            print(f"✅ Response Received ({code.name} successful)")
            print("------------------------------------------")
            print(f"Endpoint: {uri}")
            print(f"Time taken: {end_time - start_time:.3f} seconds")
            print(f"Reply Code: {response.code}")

        try:
            parsed_payload = json.loads(response.payload.decode("utf-8"))
            print(f"Payload:\n{json.dumps(parsed_payload, indent=4)}")
        except json.JSONDecodeError:
            print(f"Payload (Text):\n{response.payload.decode('utf-8')}")

        print("------------------------------------------")

    except Exception as e:
        print("❌ Failed to receive response after timeout or network error.")
        print(f"Error details: {e.__class__.__name__}: {e}")


async def main() -> None:
    """
    Runs a CoAP request (GET or POST) to an endpoint provided as a
    command-line argument.
    """
    if len(sys.argv) < 2:
        print("🛑 ERROR: Please provide the CoAP endpoint as the first argument.")
        print("Usage (GET): uv run coap_client.py <endpoint>")
        print(
            "Usage (POST): uv run coap_client.py <endpoint> <path/to/event_config.json>"
        )
        sys.exit(1)

    endpoint = sys.argv[1]
    event_path: str | None = sys.argv[2] if len(sys.argv) > 2 else None
    protocol = await aiocoap.Context.create_client_context()

    try:
        if event_path:
            # Event Trigger
            if not os.path.exists(event_path):
                print(
                    f"🛑 ERROR: Event configuration file not found at '{event_path}'."
                )
                return

            try:
                with open(event_path, "r") as f:
                    event_config = json.load(f)

                post_payload = json.dumps(event_config).encode("utf-8")
                await send_request(protocol, aiocoap.Code.POST, endpoint, post_payload)

            except json.JSONDecodeError as e:
                print(f"🛑 ERROR: Failed to parse JSON file: {e}")
                return

        else:
            # Send the GET request
            await send_request(protocol, aiocoap.Code.GET, endpoint)
    finally:
        await protocol.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Client Shutting Down...")
