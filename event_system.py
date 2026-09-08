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

EVENT_VERSION = 1
STEP_TYPES = frozenset({"dialogue", "battle"})


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
    position = raw.get("position", [0, 0])
    try:
        x, y = int(position[0]), int(position[1])
    except (IndexError, TypeError, ValueError):
        x, y = 0, 0
    steps = [step for item in raw.get("steps", []) if (step := normalize_step(item))]
    event = {
        "id": event_id,
        "name": name,
        "map": str(raw.get("map", "world")).strip() or "world",
        "position": [max(0, x), max(0, y)],
        "icon": Path(str(raw.get("icon", ""))).name,
        "once": bool(raw.get("once", True)),
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


def event_index(events: Iterable[dict]) -> dict[tuple[str, tuple[int, int]], dict]:
    return {
        (event["map"], tuple(event["position"])): event
        for event in events
        if event.get("steps")
    }


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
