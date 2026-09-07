"""Convert the Essentials reference text files into editable JSON battle data.

The source files are kept in ``assets/resource/reference_data``.  This script
only copies gameplay-facing fields, so the generated JSON remains readable and
can be edited with a normal text editor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "assets" / "resource" / "reference_data"
OUTPUT = ROOT / "assets" / "data"


def parse_blocks(path: Path) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"\[([^]]+)\]", line)
        if match:
            if current is not None:
                blocks.append(current)
            current = {"id": match.group(1).strip().upper()}
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = value.strip()
    if current is not None:
        blocks.append(current)
    return blocks


def csv_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def int_value(raw: str | None, default: int = 0) -> int:
    try:
        return int(raw or default)
    except ValueError:
        return default


def build_pokemon() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for block in parse_blocks(REFERENCE / "pokemon.txt"):
        base_stats = [int_value(value) for value in csv_values(block.get("BaseStats", ""))]
        if len(base_stats) != 6:
            continue
        types = csv_values(block.get("Types", ""))
        abilities = csv_values(block.get("Abilities", ""))
        hidden = csv_values(block.get("HiddenAbilities", ""))
        result[block["id"]] = {
            "id": block["id"],
            "name": block.get("Name", block["id"]),
            "types": types,
            "base_stats": {
                "hp": base_stats[0],
                "attack": base_stats[1],
                "defense": base_stats[2],
                "speed": base_stats[3],
                "special_attack": base_stats[4],
                "special_defense": base_stats[5],
            },
            "abilities": abilities,
            "hidden_abilities": hidden,
            "pokedex": block.get("Pokedex", ""),
            "generation": int_value(block.get("Generation"), 0),
        }
    return result


def build_moves() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for block in parse_blocks(REFERENCE / "moves.txt"):
        result[block["id"]] = {
            "id": block["id"],
            "name": block.get("Name", block["id"]),
            "type": block.get("Type", "NORMAL").upper(),
            "category": block.get("Category", "Status").title(),
            "power": int_value(block.get("Power"), 0),
            "accuracy": int_value(block.get("Accuracy"), 100),
            "pp": int_value(block.get("TotalPP"), 0),
            "priority": int_value(block.get("Priority"), 0),
            "description": block.get("Description", ""),
        }
    return result


def write_json(name: str, payload: dict[str, dict], description: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": 1,
        "description": description,
        "stat_order": ["hp", "attack", "defense", "speed", "special_attack", "special_defense"],
        "entries": payload,
    }
    (OUTPUT / name).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{name}: {len(payload)} entries")


def main() -> None:
    write_json("pokemon.json", build_pokemon(), "可编辑的宝可梦图鉴与六项种族值；BaseStats 顺序为 HP/攻击/防御/速度/特攻/特防。")
    write_json("moves.json", build_moves(), "可编辑的普通招式数据；Power=0 表示变化类招式，不参与直接伤害公式。")


if __name__ == "__main__":
    main()
