import logging
import asyncio
from typing import Protocol

logger = logging.getLogger("iot-sim")

class BatteryModel:
    def __init__(
        self,
        initial_charge: float,
        idle_rate: float,
        transmit_rate: float
    ) -> None:
        """
        initial_charge: Battery level in percentage (0-100)
        idle_rate: idle discharge rate in percentage per minute
        transmit_rate: energy cost per transmission in percentage
        """
        self.charge = max(0.0, min(100.0, initial_charge))
        self.idle_rate = idle_rate
        self.transmit_rate = transmit_rate
        self.is_discharged = self.charge <= 0

    def consume_transmit(self) -> None:
        """Models transmit-discharge event."""
        self._decrease(self.transmit_rate)

    def consume_idle(self) -> None:
        """Models idle-discharge event."""
        self._decrease(self.idle_rate)

    def _decrease(self, amount: float) -> None:
        if self.is_discharged:
            return
        
        self.charge = max(0.0, min(100.0, self.charge - amount))
        if self.charge <= 0:
            self.charge = 0.0
            self.is_discharged = True
            logger.info("🔋 Battery fully discharged.")

    def update_parameters(
        self,
        idle_rate: float | None = None,
        transmit_rate: float | None = None
    ) -> None:
        if idle_rate is not None:
            self.idle_rate = idle_rate
        if transmit_rate is not None:
            self.transmit_rate = transmit_rate
