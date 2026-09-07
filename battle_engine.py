"""Data-driven, simplified Pokemon battle rules for the Pygame prototype.

The engine deliberately omits natures, abilities, held items and status
conditions.  Every Pokemon uses default 6V IVs (31 in all six stats), zero EVs,
and the standard level/stat formulas.  It is independent of the UI and can be
used by tests, a future battle screen, or a serial-controlled move selector.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "assets" / "data"

STAT_NAMES = ("hp", "attack", "defense", "speed", "special_attack", "special_defense")

# Multipliers are expressed as integer quarters to keep the result predictable
# and avoid floating point drift in the damage formula.
TYPE_EFFECTIVENESS: dict[str, dict[str, float]] = {
    "NORMAL": {"ROCK": 0.5, "GHOST": 0.0, "STEEL": 0.5},
    "FIRE": {"FIRE": 0.5, "WATER": 0.5, "GRASS": 2.0, "ICE": 2.0, "BUG": 2.0, "ROCK": 0.5, "DRAGON": 0.5, "STEEL": 2.0},
    "WATER": {"FIRE": 2.0, "WATER": 0.5, "GRASS": 0.5, "GROUND": 2.0, "ROCK": 2.0, "DRAGON": 0.5},
    "ELECTRIC": {"WATER": 2.0, "ELECTRIC": 0.5, "GRASS": 0.5, "GROUND": 0.0, "FLYING": 2.0, "DRAGON": 0.5},
    "GRASS": {"FIRE": 0.5, "WATER": 2.0, "GRASS": 0.5, "POISON": 0.5, "GROUND": 2.0, "ROCK": 2.0, "BUG": 0.5, "DRAGON": 0.5, "STEEL": 0.5},
    "ICE": {"FIRE": 0.5, "WATER": 0.5, "GRASS": 2.0, "ICE": 0.5, "GROUND": 2.0, "FLYING": 2.0, "DRAGON": 2.0, "STEEL": 0.5},
    "FIGHTING": {"NORMAL": 2.0, "ICE": 2.0, "POISON": 0.5, "FLYING": 0.5, "PSYCHIC": 0.5, "BUG": 0.5, "ROCK": 2.0, "GHOST": 0.0, "DARK": 2.0, "STEEL": 2.0, "FAIRY": 0.5},
    "POISON": {"GRASS": 2.0, "POISON": 0.5, "GROUND": 0.5, "ROCK": 0.5, "GHOST": 0.5, "STEEL": 0.0, "FAIRY": 2.0},
    "GROUND": {"FIRE": 2.0, "ELECTRIC": 2.0, "GRASS": 0.5, "POISON": 2.0, "FLYING": 0.0, "BUG": 0.5, "ROCK": 2.0, "STEEL": 2.0},
    "FLYING": {"ELECTRIC": 0.5, "GRASS": 2.0, "FIGHTING": 2.0, "BUG": 2.0, "ROCK": 0.5, "STEEL": 0.5},
    "PSYCHIC": {"FIGHTING": 2.0, "POISON": 2.0, "PSYCHIC": 0.5, "STEEL": 0.5, "DARK": 0.0},
    "BUG": {"FIRE": 0.5, "GRASS": 2.0, "FIGHTING": 0.5, "POISON": 0.5, "FLYING": 0.5, "PSYCHIC": 2.0, "GHOST": 0.5, "DARK": 2.0, "STEEL": 0.5, "FAIRY": 0.5},
    "ROCK": {"FIRE": 2.0, "ICE": 2.0, "FIGHTING": 0.5, "GROUND": 0.5, "FLYING": 2.0, "BUG": 2.0, "STEEL": 0.5},
    "GHOST": {"NORMAL": 0.0, "PSYCHIC": 2.0, "GHOST": 2.0, "DARK": 0.5},
    "DRAGON": {"DRAGON": 2.0, "STEEL": 0.5, "FAIRY": 0.0},
    "DARK": {"FIGHTING": 0.5, "PSYCHIC": 2.0, "GHOST": 2.0, "DARK": 0.5, "FAIRY": 0.5},
    "STEEL": {"FIRE": 0.5, "WATER": 0.5, "ELECTRIC": 0.5, "ICE": 2.0, "ROCK": 2.0, "STEEL": 0.5, "FAIRY": 2.0},
    "FAIRY": {"FIRE": 0.5, "FIGHTING": 2.0, "POISON": 0.5, "DRAGON": 2.0, "DARK": 2.0, "STEEL": 0.5},
}


@dataclass(frozen=True)
class Move:
    id: str
    name: str
    type: str = "NORMAL"
    category: str = "Status"
    power: int = 0
    accuracy: int = 100
    pp: int = 0
    priority: int = 0
    critical_stage: int = 0
    description: str = ""

    @property
    def is_damaging(self) -> bool:
        return self.power > 0 and self.category.lower() in {"physical", "special"}


@dataclass(frozen=True)
class Species:
    id: str
    name: str
    types: tuple[str, ...]
    base_stats: Mapping[str, int]
    abilities: tuple[str, ...] = ()
    hidden_abilities: tuple[str, ...] = ()
    pokedex: str = ""
    generation: int = 0


@dataclass
class Pokemon:
    species: Species
    level: int = 50
    ivs: dict[str, int] = field(default_factory=lambda: {stat: 31 for stat in STAT_NAMES})
    evs: dict[str, int] = field(default_factory=lambda: {stat: 0 for stat in STAT_NAMES})
    current_hp: int | None = None

    def __post_init__(self) -> None:
        self.level = max(1, min(100, int(self.level)))
        for stat in STAT_NAMES:
            self.ivs[stat] = max(0, min(31, int(self.ivs.get(stat, 31))))
            self.evs[stat] = max(0, min(252, int(self.evs.get(stat, 0))))
        if self.current_hp is None:
            self.current_hp = self.stats["hp"]
        self.current_hp = max(0, min(self.max_hp, int(self.current_hp)))

    @property
    def stats(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for stat in STAT_NAMES:
            base = int(self.species.base_stats[stat])
            core = ((2 * base + self.ivs[stat] + self.evs[stat] // 4) * self.level) // 100
            result[stat] = core + self.level + 10 if stat == "hp" else core + 5
        return result

    @property
    def max_hp(self) -> int:
        return self.stats["hp"]


@dataclass(frozen=True)
class DamageResult:
    damage: int
    base_damage: int
    random_factor: int
    stab: float
    type_multiplier: float
    critical: bool = False
    critical_multiplier: float = 1.0


@dataclass(frozen=True)
class TurnResult:
    attacker: str
    defender: str
    move: str
    damage: DamageResult | None
    defender_hp: int
    message: str
    hit: bool = True
    critical: bool = False


def _load_entries(filename: str) -> dict[str, dict]:
    document = json.loads((DATA / filename).read_text(encoding="utf-8"))
    return document.get("entries", document)


def load_species(species_id: str, path: Path | None = None) -> Species:
    entries = _load_entries(path.name if path else "pokemon.json") if path else _load_entries("pokemon.json")
    raw = entries[species_id.upper()]
    return Species(
        id=raw["id"], name=raw["name"], types=tuple(raw["types"]),
        base_stats=raw["base_stats"], abilities=tuple(raw.get("abilities", [])),
        hidden_abilities=tuple(raw.get("hidden_abilities", [])),
        pokedex=raw.get("pokedex", ""), generation=raw.get("generation", 0),
    )


def load_move(move_id: str) -> Move:
    raw = _load_entries("moves.json")[move_id.upper()]
    return Move(
        id=raw["id"], name=raw["name"], type=raw["type"], category=raw["category"],
        power=raw["power"], accuracy=raw["accuracy"], pp=raw["pp"],
        priority=raw.get("priority", 0), critical_stage=raw.get("critical_stage", 0),
        description=raw.get("description", ""),
    )


def type_multiplier(move_type: str, defender_types: tuple[str, ...]) -> float:
    chart = TYPE_EFFECTIVENESS.get(move_type.upper(), {})
    result = 1.0
    for defender_type in defender_types:
        result *= chart.get(defender_type.upper(), 1.0)
    return result


def calculate_damage(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    *,
    random_factor: int | None = None,
    critical: bool = False,
) -> DamageResult:
    """Apply the main games' damage shape without natures or abilities.

    ``random_factor`` is 217..255, or defaults to a uniformly chosen value.
    Passing 255 makes tests and UI previews deterministic.
    """
    if not move.is_damaging:
        return DamageResult(0, 0, 255 if random_factor is None else random_factor, 1.0, 1.0, critical, 1.5 if critical else 1.0)
    random_factor = random.randint(217, 255) if random_factor is None else max(217, min(255, random_factor))
    attack_stat = "attack" if move.category.lower() == "physical" else "special_attack"
    defense_stat = "defense" if move.category.lower() == "physical" else "special_defense"
    base = (((2 * attacker.level // 5 + 2) * move.power * attacker.stats[attack_stat]) // defender.stats[defense_stat]) // 50 + 2
    critical_multiplier = 1.5 if critical else 1.0
    if critical:
        base = int(base * critical_multiplier)
    stab = 1.5 if move.type.upper() in attacker.species.types else 1.0
    multiplier = type_multiplier(move.type, defender.species.types)
    damage = max(1, int(base * stab * multiplier * random_factor / 255)) if multiplier else 0
    return DamageResult(damage, base, random_factor, stab, multiplier, critical, critical_multiplier)


def roll_accuracy(move: Move, rng: random.Random | None = None, roll: int | None = None) -> bool:
    """Roll a move's accuracy as an inclusive 1..100 percentage check."""
    if move.accuracy >= 100:
        return True
    if move.accuracy <= 0:
        return False
    value = roll if roll is not None else (rng or random).randint(1, 100)
    return value <= move.accuracy


def roll_critical(
    move: Move,
    rng: random.Random | None = None,
    roll: int | None = None,
) -> bool:
    """Roll the standard Gen VI+ critical stages (default rate is 1/24)."""
    # Critical stages use 1/24, 1/8, 1/2 and 1/1 odds in the main games.
    denominators = (24, 8, 2, 1)
    denominator = denominators[min(max(move.critical_stage, 0), len(denominators) - 1)]
    if denominator == 1:
        return True
    value = roll if roll is not None else (rng or random).randrange(denominator)
    return value == 0


class Battle:
    """Small two-Pokemon turn engine for the future UI."""

    def __init__(self, player: Pokemon, opponent: Pokemon, moves: Mapping[str, Move]):
        self.player = player
        self.opponent = opponent
        self.moves = moves
        self.turn = 1
        self.finished = False

    def use_player_move(
        self,
        move_id: str,
        *,
        random_factor: int | None = None,
        accuracy_roll: int | None = None,
        critical_roll: int | None = None,
        rng: random.Random | None = None,
    ) -> TurnResult:
        if self.finished:
            raise RuntimeError("battle is already finished")
        move = self.moves[move_id.upper()]
        if not roll_accuracy(move, rng, accuracy_roll):
            result = TurnResult(self.player.species.name, self.opponent.species.name, move.id, None,
                                self.opponent.current_hp, f"{self.player.species.name} 使用了 {move.name}，但是没有命中！", False, False)
            self.turn += 1
            return result
        critical = roll_critical(move, rng, critical_roll) if move.is_damaging else False
        damage = calculate_damage(self.player, self.opponent, move,
                                  random_factor=random_factor, critical=critical)
        self.opponent.current_hp = max(0, self.opponent.current_hp - damage.damage)
        if self.opponent.current_hp == 0:
            self.finished = True
        critical_text = " 要害命中！" if critical else ""
        result = TurnResult(self.player.species.name, self.opponent.species.name, move.id, damage,
                            self.opponent.current_hp, f"{self.player.species.name} 使用了 {move.name}！{critical_text}", True, critical)
        self.turn += 1
        return result


def default_demo_battle() -> Battle:
    player = Pokemon(load_species("FERROTHORN"), level=50)
    opponent = Pokemon(load_species("FERROSEED"), level=20)
    moves = {move_id: load_move(move_id) for move_id in ("SOLARBEAM", "HEAVYSLAM", "WEATHERBALL")}
    return Battle(player, opponent, moves)
