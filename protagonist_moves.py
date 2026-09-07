"""Runtime definitions for the STC-B protagonist's sensor-linked moves.

These moves intentionally live in Python instead of JSON: board readings are
live values and must be validated and transformed before a battle move exists.
Static Pokemon and ordinary move data remain in JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

from battle_engine import Move


@dataclass(frozen=True)
class SensorSnapshot:
    """One sampled STC-B state. Missing sensors use neutral defaults."""

    light: int | None = None
    temperature: float | None = None
    vibration_count: int = 0
    heavy_ready: bool = False

    @property
    def light_value(self) -> int:
        return max(0, min(1023, 512 if self.light is None else int(self.light)))

    @property
    def temperature_value(self) -> float:
        return 20.0 if self.temperature is None else float(self.temperature)


@dataclass(frozen=True)
class ProtagonistMove:
    id: str
    name: str
    base_type: str
    category: str
    base_power: int
    hardware: str
    description: str

    def resolve(self, sensors: SensorSnapshot) -> Move:
        """Turn the current hardware state into a normal battle ``Move``."""
        move_type = self.base_type
        power = self.base_power
        if self.id == "STC_SYNTHESIS":
            power = 0
        elif self.id == "STC_SOLARBEAM":
            power = round(self.base_power * (0.5 + sensors.light_value / 2046.0))
        elif self.id == "STC_HEAVYSLAM":
            power += min(40, max(0, sensors.vibration_count) * 4)
        elif self.id == "STC_WEATHERBALL":
            temperature = sensors.temperature_value
            if temperature > 30:
                move_type = "FIRE"
                power = self.base_power * 2
            elif temperature < 10:
                move_type = "ICE"
                power = self.base_power * 2
        return Move(
            id=self.id, name=self.name, type=move_type, category=self.category,
            power=power, accuracy=100, pp=5, description=self.description,
        )

    def available(self, sensors: SensorSnapshot) -> bool:
        return self.id != "STC_HEAVYSLAM" or sensors.heavy_ready


PROTAGONIST_MOVES: dict[str, ProtagonistMove] = {
    "STC_SYNTHESIS": ProtagonistMove("STC_SYNTHESIS", "光合作用", "GRASS", "Status", 0, "light", "根据光敏传感器数值恢复体力。"),
    "STC_SOLARBEAM": ProtagonistMove("STC_SOLARBEAM", "日光束", "GRASS", "Special", 120, "light", "光照越强，招式威力越高。"),
    "STC_HEAVYSLAM": ProtagonistMove("STC_HEAVYSLAM", "重磅冲撞", "STEEL", "Physical", 80, "vibration", "检测到震动后才可使用，震动次数会增加威力。"),
    "STC_WEATHERBALL": ProtagonistMove("STC_WEATHERBALL", "气象球", "NORMAL", "Special", 50, "temperature", "高温为火属性，低温为冰属性，否则为一般属性。"),
}


def protagonist_move(move_id: str, sensors: SensorSnapshot) -> Move:
    """Resolve a sensor-linked move, raising ``KeyError`` for unknown IDs."""
    move = PROTAGONIST_MOVES[move_id.upper()]
    if not move.available(sensors):
        raise RuntimeError("STC_HEAVYSLAM requires a vibration event first")
    return move.resolve(sensors)
