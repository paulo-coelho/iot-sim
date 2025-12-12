from aiomqtt import Client, MqttError

from typing import Any


class AsyncMQTTClient:
    def __init__(self, broker_address: str = "localhost:1883") -> None:
        self.broker_address: str = broker_address
        self._host: str
        port: str
        self._host, port = self.broker_address.split(":")
        self._port: int = int(port)
        self._client = None
        self._client_cm = None
        self._connected: bool = False

    async def __aenter__(self) -> "AsyncMQTTClient":
        self._client = Client(self._host, self._port)
        self._client_cm = self._client.__aenter__()
        await self._client_cm
        self._connected = True
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        if self._client:
            await self._client.__aexit__(exc_type, exc, tb)
            self._connected = False
            self._client = None
            self._client_cm = None

    async def publish(self, topic: str, payload: str) -> None:
        if not self._connected or self._client is None:
            raise RuntimeError(
                "MQTT client is not connected. Use 'async with AsyncMQTTClient(...) as client:'"
            )
        try:
            await self._client.publish(topic, payload)
        except MqttError as e:
            print(f"MQTT publish error: {e}")
            raise
