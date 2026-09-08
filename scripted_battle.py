"""Pure state machines for story-specific scripted battles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GROTLE_TUTORIAL_PATH = ROOT / "assets" / "battles" / "grotle_tutorial.json"


@dataclass(frozen=True)
class BattleAction:
    actor: str
    move_id: str
    move_name: str
    effect: str
    target: str
    amount: int
    kind: str
    message: str


def load_scripted_battle(path: Path = GROTLE_TUTORIAL_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class GrotleTutorial:
    """The opening tutorial battle as a resumable, explicit state machine."""

    MOVE_STAGES = frozenset({"require_solar", "require_synthesis", "free_battle"})

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or load_scripted_battle()
        self.player_max_hp = int(self.config["player"]["max_hp"])
        self.foe_max_hp = int(self.config["opponent"]["max_hp"])
        self.reset()

    def reset(self) -> None:
        self.player_hp = self.player_max_hp
        self.foe_hp = self.foe_max_hp
        self.stage = "intro_absorb"
        self.after_action: str | None = None
        self.hint: str | None = None

    @property
    def mode(self) -> str:
        if self.stage == "action":
            return "action"
        if self.stage in self.MOVE_STAGES:
            return "moves"
        return "message"

    @property
    def message(self) -> str:
        key = self.hint or self.stage
        return str(self.config["messages"].get(key, ""))

    @property
    def outcome(self) -> str | None:
        return self.stage if self.stage in {"won", "lost"} else None

    @property
    def required_move(self) -> str | None:
        if self.stage == "require_solar":
            return "solar_beam"
        if self.stage == "require_synthesis":
            return "synthesis"
        return None

    @property
    def available_moves(self) -> tuple[str, ...]:
        if self.stage == "require_solar":
            return ("solar_beam",)
        if self.stage in {"require_synthesis", "free_battle"}:
            return ("solar_beam", "synthesis")
        return ()

    def move_spec(self, move_id: str) -> dict:
        return self.config["moves"][move_id]

    @staticmethod
    def _sensor_value(light: int | None, low: int, high: int) -> int:
        value = 512 if light is None else max(0, min(1023, int(light)))
        return low + round((high - low) * value / 1023)

    def confirm(self) -> BattleAction | None:
        self.hint = None
        transitions = {
            "intro_absorb": "intro_focus",
            "intro_focus": "enemy_demo_announce",
            "try_solar": "solar_help",
            "solar_help": "require_solar",
            "praise": "synthesis_explain",
            "synthesis_explain": "enemy_second_announce",
            "synthesis_prompt": "synthesis_help",
            "synthesis_help": "require_synthesis",
            "free_help": "free_battle",
        }
        if self.stage in transitions:
            self.stage = transitions[self.stage]
            return None
        if self.stage == "enemy_demo_announce":
            return self._opponent_solar("try_solar")
        if self.stage == "enemy_second_announce":
            return self._opponent_solar("synthesis_prompt")
        if self.stage == "enemy_free_announce":
            return self._opponent_solar("free_battle")
        return None

    def choose_move(self, move_id: str, light: int | None) -> BattleAction | None:
        if self.mode != "moves" or move_id not in self.available_moves:
            return None
        required = self.required_move
        if required and move_id != required:
            self.hint = "wrong_solar" if required == "solar_beam" else "wrong_synthesis"
            return None
        self.hint = None
        spec = self.move_spec(move_id)
        if move_id == "solar_beam":
            amount = self._sensor_value(light, int(spec["damage_min"]), int(spec["damage_max"]))
            self.foe_hp = max(0, self.foe_hp - amount)
            if self.foe_hp == 0:
                after = "won"
            elif self.stage == "require_solar":
                after = "praise"
            else:
                after = "enemy_free_announce"
            kind = "damage"
            target = "foe"
        else:
            amount = self._sensor_value(light, int(spec["heal_min"]), int(spec["heal_max"]))
            before = self.player_hp
            self.player_hp = min(self.player_max_hp, self.player_hp + amount)
            amount = self.player_hp - before
            after = "free_help" if self.stage == "require_synthesis" else "enemy_free_announce"
            kind = "heal"
            target = "player"
        self.after_action = after
        self.stage = "action"
        return BattleAction(
            actor="player",
            move_id=move_id,
            move_name=str(spec["name"]),
            effect=str(spec["effect"]),
            target=target,
            amount=amount,
            kind=kind,
            message=f"{self.config['player']['name']}使出了{spec['name']}！",
        )

    def _opponent_solar(self, after: str) -> BattleAction:
        spec = self.config["opponent_move"]
        amount = min(self.player_hp, int(spec["damage"]))
        self.player_hp -= amount
        self.after_action = "lost" if self.player_hp == 0 else after
        self.stage = "action"
        return BattleAction(
            actor="opponent",
            move_id="opponent_solar",
            move_name=str(spec["name"]),
            effect=str(spec["effect"]),
            target="player",
            amount=amount,
            kind="damage",
            message=f"{self.config['opponent']['name']}使出了{spec['name']}！",
        )

    def complete_action(self) -> None:
        if self.stage != "action" or self.after_action is None:
            return
        self.stage = self.after_action
        self.after_action = None
