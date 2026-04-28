import random
import asyncio
import logging
from typing import Any

logger = logging.getLogger("iot-sim")

class NetworkModel:
    def __init__(
        self,
        drop_percentage: float,
        delay_profiles: list[dict[str, int | float]]
    ) -> None:
        self.drop_percentage = drop_percentage
        self.set_delay_profiles(delay_profiles)

    def set_delay_profiles(self, profiles: list[dict[str, int | float]]) -> None:
        """Sets up the weighted random choice for delay profiles."""
        self.delay_profiles = profiles
        self.delay_weights: list[int | float] = [p["probability"] for p in profiles]
        self.delay_ranges: list[tuple[float, float]] = [
            (p["min"], p["max"]) for p in profiles
        ]

    def should_drop(self) -> bool:
        """Probabilistic drop decision."""
        return random.random() * 100 < self.drop_percentage

    async def apply_delay(self) -> float:
        """Selects and applies a random delay based on profiles."""
        if not self.delay_ranges:
            return 0.0
        
        selected_range: tuple[float, float] = random.choices(
            self.delay_ranges, weights=self.delay_weights, k=1
        )[0]
        
        delay = random.uniform(selected_range[0], selected_range[1])
        if delay > 0:
            logger.debug(
                f"⏳ Non-blocking delay: {delay:.2f}s (Profile: {selected_range[0]:.2f}s - {selected_range[1]:.2f}s)"
            )
            await asyncio.sleep(delay)
        return delay

    def update_parameters(
        self,
        drop_percentage: float | None = None,
        delay_profiles: list[dict[str, int | float]] | None = None
    ) -> None:
        if drop_percentage is not None:
            self.drop_percentage = drop_percentage
        if delay_profiles is not None:
            self.set_delay_profiles(delay_profiles)
