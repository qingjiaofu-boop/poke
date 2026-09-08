"""Shared data model for map-triggered, ordered story events."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
EVENTS_PATH = ASSETS / "map_events.json"
MAPS_PATH = ASSETS / "maps" / "outdoor_maps.json"
WORLD_PATH = ASSETS / "maps" / "world_connections.json"
PRELOAD_DIR = ASSETS / "resource" / "dialogue" / "preloads"
ICON_DIR = ASSETS / "resource" / "event" / "icon"

EVENT_VERSION = 2
TRIGGER_TYPES = frozenset({
    "step", "game_start", "warp_attempt", "warp_arrival", "rock_break",
})
STEP_TYPES = frozenset({
    "dialogue",
    "battle",
    "toast",
    "set_flag",
    "wait",
    "camera_pan",
    "camera_shake",
    "play_animation",
    "actor_move",
    "actor_visibility",
    "break_rock",
})


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return value.lower() or "event"


def unique_event_id(name: str, existing: Iterable[str]) -> str:
    existing = set(existing)
    base = _slug(name)
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _position(raw: object) -> list[int]:
    try:
        x, y = int(raw[0]), int(raw[1])
    except (IndexError, TypeError, ValueError):
        x, y = 0, 0
    return [max(0, x), max(0, y)]


def _duration(raw: object, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(0, min(60_000, value))


def _flag_list(raw: object) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, (list, tuple, set)):
        return []
    result = []
    for value in raw:
        flag = _slug(str(value))
        if flag != "event" and flag not in result:
            result.append(flag)
    return result


def normalize_step(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    step_type = str(raw.get("type", "dialogue")).strip().lower()
    if step_type not in STEP_TYPES:
        return None
    if step_type == "battle":
        return {
            "type": "battle",
            "battle_id": str(raw.get("battle_id", "placeholder")).strip() or "placeholder",
        }
    if step_type == "toast":
        return {
            "type": "toast",
            "text": str(raw.get("text", "")).strip(),
            "duration_ms": _duration(raw.get("duration_ms"), 1800),
        }
    if step_type == "set_flag":
        return {
            "type": "set_flag",
            "flag": _slug(str(raw.get("flag", "story_flag"))),
            "value": bool(raw.get("value", True)),
        }
    if step_type == "wait":
        return {
            "type": "wait",
            "duration_ms": _duration(raw.get("duration_ms"), 500),
        }
    if step_type == "camera_pan":
        target = str(raw.get("target", "position")).strip().lower()
        return {
            "type": "camera_pan",
            "target": "player" if target == "player" else "position",
            "position": _position(raw.get("position", [0, 0])),
            "duration_ms": _duration(raw.get("duration_ms"), 800),
        }
    if step_type == "camera_shake":
        try:
            intensity = int(raw.get("intensity", 6))
        except (TypeError, ValueError):
            intensity = 6
        return {
            "type": "camera_shake",
            "duration_ms": _duration(raw.get("duration_ms"), 420),
            "intensity": max(0, min(32, intensity)),
        }
    if step_type == "play_animation":
        return {
            "type": "play_animation",
            "animation": _slug(str(raw.get("animation", "meteor"))),
            "position": _position(raw.get("position", [0, 0])),
            "duration_ms": _duration(raw.get("duration_ms"), 1000),
        }
    if step_type == "actor_move":
        return {
            "type": "actor_move",
            "actor": _slug(str(raw.get("actor", "event"))),
            "position": _position(raw.get("position", [0, 0])),
            "duration_ms": _duration(raw.get("duration_ms"), 600),
        }
    if step_type == "actor_visibility":
        return {
            "type": "actor_visibility",
            "actor": _slug(str(raw.get("actor", "event"))),
            "visible": bool(raw.get("visible", True)),
        }
    if step_type == "break_rock":
        return {
            "type": "break_rock",
            "position": _position(raw.get("position", [0, 0])),
            "duration_ms": _duration(raw.get("duration_ms"), 500),
        }
    text = str(raw.get("text", "")).strip()
    return {
        "type": "dialogue",
        "preload": Path(str(raw.get("preload", "no_portrait_bottom.png"))).name,
        "speaker": str(raw.get("speaker", "")).strip(),
        "text": text,
    }


def normalize_event(raw: object, used_ids: set[str] | None = None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    used_ids = used_ids if used_ids is not None else set()
    name = str(raw.get("name", "未命名事件")).strip() or "未命名事件"
    event_id = _slug(str(raw.get("id", "")))
    if not event_id or event_id == "event":
        event_id = unique_event_id(name, used_ids)
    elif event_id in used_ids:
        event_id = unique_event_id(event_id, used_ids)
    trigger = str(raw.get("trigger", "step")).strip().lower()
    if trigger not in TRIGGER_TYPES:
        trigger = "step"
    position = _position(raw.get("position", [0, 0]))
    conditions = raw.get("conditions", {})
    if not isinstance(conditions, dict):
        conditions = {}
    steps = [step for item in raw.get("steps", []) if (step := normalize_step(item))]
    event = {
        "id": event_id,
        "name": name,
        "trigger": trigger,
        "map": str(raw.get("map", "world")).strip() or "world",
        "position": position,
        "icon": Path(str(raw.get("icon", ""))).name,
        "once": bool(raw.get("once", True)),
        "conditions": {
            "all": _flag_list(conditions.get("all", raw.get("required_flags", []))),
            "none": _flag_list(conditions.get("none", raw.get("forbidden_flags", []))),
        },
        "steps": steps,
    }
    used_ids.add(event_id)
    return event


def load_event_document(path: Path = EVENTS_PATH) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = {}
    used_ids: set[str] = set()
    events = []
    entries = raw.get("events", []) if isinstance(raw, dict) else []
    for item in entries if isinstance(entries, list) else []:
        event = normalize_event(item, used_ids)
        if event is not None:
            events.append(event)
    return {"version": EVENT_VERSION, "events": events}


def save_event_document(document: dict, path: Path = EVENTS_PATH) -> dict:
    used_ids: set[str] = set()
    events = []
    for item in document.get("events", []) if isinstance(document, dict) else []:
        event = normalize_event(item, used_ids)
        if event is not None:
            events.append(event)
    normalized = {"version": EVENT_VERSION, "events": events}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return normalized


def conditions_met(event: dict, flags: Iterable[str]) -> bool:
    active = set(flags)
    conditions = event.get("conditions", {})
    required = set(conditions.get("all", []))
    forbidden = set(conditions.get("none", []))
    return required <= active and not (forbidden & active)


def event_index(
    events: Iterable[dict],
    trigger: str = "step",
) -> dict[tuple[str, tuple[int, int]], dict]:
    return {
        (event["map"], tuple(event["position"])): event
        for event in events
        if event.get("steps") and event.get("trigger", "step") == trigger
    }


def events_for_trigger(
    events: Iterable[dict],
    trigger: str,
    *,
    map_name: str | None = None,
    position: tuple[int, int] | None = None,
    flags: Iterable[str] = (),
) -> list[dict]:
    result = []
    for event in events:
        if event.get("trigger", "step") != trigger or not event.get("steps"):
            continue
        if map_name is not None and event.get("map") != map_name:
            continue
        if position is not None and tuple(event.get("position", ())) != tuple(position):
            continue
        if conditions_met(event, flags):
            result.append(event)
    return result


def map_sizes() -> dict[str, tuple[int, int]]:
    try:
        maps = json.loads(MAPS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        maps = {}
    result = {}
    for name, spec in maps.items() if isinstance(maps, dict) else ():
        try:
            result[str(name)] = (int(spec["size"][0]), int(spec["size"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    try:
        world = json.loads(WORLD_PATH.read_text(encoding="utf-8"))
        result["world"] = tuple(int(value) for value in world["world_size"])
    except (OSError, KeyError, ValueError, TypeError):
        pass
    return result
