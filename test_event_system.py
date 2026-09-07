"""Pure data-model checks for the map event editor/runtime contract."""
from pathlib import Path
from tempfile import TemporaryDirectory

from event_system import (
    event_index,
    load_event_document,
    normalize_event,
    save_event_document,
    unique_event_id,
)


def test_event_document_round_trip():
    document = {
        "events": [{
            "id": "meeting",
            "name": "矿洞相遇",
            "map": "grancave",
            "position": [4, 9],
            "icon": "../aron.png",
            "once": True,
            "steps": [
                {"type": "dialogue", "preload": "../aron_right.png", "speaker": "可可多拉", "text": "你好！"},
                {"type": "battle", "battle_id": "aron_intro"},
            ],
        }],
    }
    with TemporaryDirectory() as directory:
        path = Path(directory) / "map_events.json"
        saved = save_event_document(document, path)
        loaded = load_event_document(path)
    assert loaded == saved
    assert loaded["events"][0]["icon"] == "aron.png"
    assert loaded["events"][0]["steps"][0]["preload"] == "aron_right.png"
    assert event_index(loaded["events"])[("grancave", (4, 9))]["id"] == "meeting"


def test_normalization_and_unique_ids():
    used = set()
    first = normalize_event({"name": "测试事件", "steps": [{"type": "unknown"}]}, used)
    second = normalize_event({"name": "测试事件"}, used)
    assert first["id"] == "event"
    assert second["id"] == "event_2"
    assert first["position"] == [0, 0]
    assert first["steps"] == []
    assert unique_event_id("boss", {"boss", "boss_2"}) == "boss_3"


if __name__ == "__main__":
    test_event_document_round_trip()
    test_normalization_and_unique_ids()
    print("event system ok")
