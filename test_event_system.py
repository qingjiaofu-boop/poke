"""Pure data-model checks for the map event editor/runtime contract."""
from pathlib import Path
from tempfile import TemporaryDirectory

from event_system import (
    conditions_met,
    event_index,
    events_for_trigger,
    load_event_document,
    normalize_event,
    normalize_step,
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


def test_trigger_conditions_and_cutscene_steps():
    event = normalize_event({
        "id": "meteor_gate",
        "name": "矿洞传送拦截",
        "trigger": "warp_attempt",
        "map": "world",
        "position": [41, 10],
        "conditions": {"all": ["training_complete"], "none": ["meteor_seen"]},
        "steps": [
            {"type": "camera_pan", "position": [45, 7], "duration_ms": 900},
            {"type": "play_animation", "animation": "meteor", "position": [45, 7]},
            {"type": "camera_shake", "duration_ms": 400, "intensity": 8},
            {"type": "break_rock", "position": [15, 11], "duration_ms": 500},
            {"type": "set_flag", "flag": "meteor_seen"},
            {"type": "camera_pan", "target": "player", "duration_ms": 700},
        ],
    })
    assert event["trigger"] == "warp_attempt"
    assert conditions_met(event, {"training_complete"})
    assert not conditions_met(event, {"training_complete", "meteor_seen"})
    assert events_for_trigger(
        [event], "warp_attempt", map_name="world", position=(41, 10),
        flags={"training_complete"},
    ) == [event]
    assert not event_index([event])
    assert normalize_step({"type": "wait", "duration_ms": -1})["duration_ms"] == 0
    assert normalize_step({"type": "break_rock", "position": [15, 11]}) == {
        "type": "break_rock", "position": [15, 11], "duration_ms": 500,
    }

    rock_event = normalize_event({
        "id": "pendant", "name": "发现吊坠", "trigger": "rock_break",
        "map": "caveB2f", "position": [15, 5],
        "steps": [{"type": "set_flag", "flag": "comet_pendant_obtained"}],
    })
    assert events_for_trigger(
        [rock_event], "rock_break", map_name="caveB2f", position=(15, 5),
    ) == [rock_event]


def test_authored_aron_event_chain():
    events = {event["id"]: event for event in load_event_document()["events"]}
    encounter = events["aron_encounter"]
    assert encounter["map"] == "caveB2f"
    assert encounter["position"] == [16, 12]
    assert any(step == {"type": "battle", "battle_id": "aron"}
               for step in encounter["steps"])
    assert any(step["type"] == "break_rock" and step["position"] == [15, 11]
               for step in encounter["steps"])
    assert any(step["type"] == "set_flag" and step["flag"] == "heavy_slam_learned"
               for step in encounter["steps"])

    pendant = events["aron_comet_pendant"]
    assert pendant["trigger"] == "rock_break"
    assert pendant["position"] == [15, 5]
    assert pendant["conditions"]["all"] == ["aron_gift_search_started"]

    gate = events["aron_gift_gate"]
    assert gate["trigger"] == "warp_attempt"
    assert gate["position"] == [34, 7]
    assert "comet_pendant_obtained" in gate["conditions"]["none"]


def test_authored_sableye_warp_arrival_event():
    event = next(
        item for item in load_event_document()["events"]
        if item["id"] == "sableye_encounter"
    )
    assert event["trigger"] == "warp_arrival"
    assert event["map"] == "caveB1F"
    assert event["position"] == [28, 7]
    assert "comet_pendant_obtained" in event["conditions"]["all"]
    assert any(step == {"type": "battle", "battle_id": "sableye"}
               for step in event["steps"])
    assert any(step["type"] == "set_flag" and step["flag"] == "sableye_befriended"
               for step in event["steps"])


if __name__ == "__main__":
    test_event_document_round_trip()
    test_normalization_and_unique_ids()
    test_trigger_conditions_and_cutscene_steps()
    test_authored_aron_event_chain()
    test_authored_sableye_warp_arrival_event()
    print("event system ok")
