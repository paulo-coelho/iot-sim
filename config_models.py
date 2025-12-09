from pydantic import BaseModel
from typing import Any
import json


class DeviceConfig(BaseModel):
    uuid: str
    temperature_range: tuple[float, float]
    battery_charge: float
    battery_transmit_discharge: float
    battery_idle_discharge: float
    drop_percentage: float
    delay_profiles: list[dict[str, int | float]]
    coordinate: dict[str, float]
    server_host: str = "0.0.0.0"
    server_port: int = 5683
    resource_path: list[str] = ["device", "data"]

    @classmethod
    def from_file(cls, filepath: str) -> "DeviceConfig":
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceConfig":
        return cls(**data)


class EventConfig(BaseModel):
    event_name: str
    event_type: str = "permanent"
    temperature_range: tuple[float, float]
    battery_transmit_discharge: float
    battery_idle_discharge: float
    drop_percentage: float
    delay_profiles: list[dict[str, int | float]]
    transition_duration_s: float
    transient_event_duration_s: float = 0
    transient_event_return_s: float = 0

    @classmethod
    def from_file(cls, filepath: str) -> "EventConfig":
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventConfig":
        return cls(**data)

    @classmethod
    def from_device_config(cls, device_config: DeviceConfig) -> "EventConfig":
        return cls(
            event_name="Normal",
            event_type="permanent",
            temperature_range=device_config.temperature_range,
            battery_transmit_discharge=device_config.battery_transmit_discharge,
            battery_idle_discharge=device_config.battery_idle_discharge,
            drop_percentage=device_config.drop_percentage,
            delay_profiles=device_config.delay_profiles,
            transition_duration_s=0,
            transient_event_duration_s=0,
            transient_event_return_s=0,
        )
