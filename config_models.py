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


class DisasterConfig(BaseModel):
    disaster_type: str
    temperature_range: tuple[float, float]
    battery_transmit_discharge: float
    battery_idle_discharge: float
    drop_percentage: float
    delay_profiles: list[dict[str, int | float]]
    transition_duration_s: float

    @classmethod
    def from_file(cls, filepath: str) -> "DisasterConfig":
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DisasterConfig":
        return cls(**data)
