import random
from typing import Protocol, Any

class SensorModel(Protocol):
    def get_reading(self) -> Any:
        ...
    
    def update_parameters(self, **kwargs) -> None:
        ...

class TemperatureSensor:
    def __init__(self, temp_min: float, temp_max: float) -> None:
        self.temp_min = temp_min
        self.temp_max = temp_max

    def get_reading(self) -> float:
        return random.uniform(self.temp_min, self.temp_max)

    def update_parameters(self, temp_min: float | None = None, temp_max: float | None = None, **kwargs) -> None:
        if temp_min is not None:
            self.temp_min = temp_min
        if temp_max is not None:
            self.temp_max = temp_max

class PressureSensor:
    def __init__(self, pressure_min: float, pressure_max: float) -> None:
        self.pressure_min = pressure_min
        self.pressure_max = pressure_max

    def get_reading(self) -> float:
        return random.uniform(self.pressure_min, self.pressure_max)

    def update_parameters(self, pressure_min: float | None = None, pressure_max: float | None = None, **kwargs) -> None:
        if pressure_min is not None:
            self.pressure_min = pressure_min
        if pressure_max is not None:
            self.pressure_max = pressure_max

class MultiSensor:
    def __init__(self, sensors: dict[str, SensorModel]) -> None:
        self.sensors = sensors

    def get_reading(self) -> dict[str, Any]:
        return {name: s.get_reading() for name, s in self.sensors.items()}

    def update_parameters(self, **kwargs) -> None:
        """
        Updates parameters for sub-sensors.
        Example kwargs: temperature_range=(20, 30), pressure_range=(1000, 1010)
        """
        if "temperature_range" in kwargs and "temperature" in self.sensors:
            tr = kwargs["temperature_range"]
            if tr:
                self.sensors["temperature"].update_parameters(temp_min=tr[0], temp_max=tr[1])
        
        if "pressure_range" in kwargs and "pressure" in self.sensors:
            pr = kwargs["pressure_range"]
            if pr:
                self.sensors["pressure"].update_parameters(pressure_min=pr[0], pressure_max=pr[1])
