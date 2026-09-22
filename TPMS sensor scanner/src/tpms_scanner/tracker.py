from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from tpms_scanner.models import Observation


@dataclass(frozen=True, slots=True)
class SensorFilter:
    models: tuple[str, ...] = ()
    sensor_ids: tuple[str, ...] = ()

    def matches(self, observation: Observation) -> bool:
        model_matches = not self.models or any(
            wanted.casefold() in observation.model.casefold() for wanted in self.models
        )
        id_matches = not self.sensor_ids or observation.sensor_id.casefold() in {
            wanted.casefold() for wanted in self.sensor_ids
        }
        return model_matches and id_matches


@dataclass(slots=True)
class SensorTracker:
    max_sensors: int = 4096
    _observations: dict[tuple[str, str], Observation] = field(default_factory=dict)
    evictions: int = 0

    def __post_init__(self) -> None:
        if self.max_sensors < 1:
            raise ValueError("max_sensors must be at least 1")

    def update(self, observation: Observation) -> bool:
        """Store an observation unless a newer reading for the same sensor exists."""
        current = self._observations.get(observation.key)
        if current is not None and observation.ordering_time < current.ordering_time:
            return False
        if current is None and len(self._observations) >= self.max_sensors:
            oldest = min(
                self._observations,
                key=lambda key: self._observations[key].ordering_time,
            )
            del self._observations[oldest]
            self.evictions += 1
        self._observations[observation.key] = observation
        return True

    def observations(self) -> tuple[Observation, ...]:
        return tuple(
            sorted(
                self._observations.values(),
                key=lambda item: (item.model.casefold(), item.sensor_id.casefold()),
            )
        )

    def extend(self, observations: Iterable[Observation]) -> int:
        return sum(self.update(observation) for observation in observations)

    def __len__(self) -> int:
        return len(self._observations)
