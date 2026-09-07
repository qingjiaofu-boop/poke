"""Regression checks for the Essentials-style STC-B story path."""
import os
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from adventure import Adventure


def advance_dialogue(game):
    while game.dialogue:
        game.command(5)


def test_story_path():
    game = Adventure(None)
    try:
        game.map_view = None
        game.pos[:] = [1, 2]
        game.facing = "up"
        game.command(5)
        assert game.father_done and game.dialogue
        advance_dialogue(game)

        game.scene = "friend"
        game.pos[:] = [2, 6]
        game.facing = "up"
        game.command(5)
        assert game.friend_met and game.dialogue
        advance_dialogue(game)
        assert game.scene == "battle"

        game.enemy_hp = 1
        game.move_cursor = 1
        game.command(5)
        assert game.battle_won
        for _ in range(32):
            game.update_battle_effect()
        game.command(5)
        assert game.scene == "route"

        game.scene = "cave3"
        game.pos[:] = [6, 5]
        game.command(9)
        assert game.rock_broken
    finally:
        game.serial.close()
        pygame.quit()


def test_tile_map_loading_and_view_switching():
    game = Adventure(None)
    try:
        expected = {"home", "friend", "route", "forest1", "route1", "moonmountain",
                    "grancave", "caveB1F", "caveB2f", "finalcave", "world"}
        assert expected <= game.tile_maps.keys()
        for tile_map in game.tile_maps.values():
            assert len({id(tile_map.layers[name]) for name in ("lower", "current", "upper")}) == 3
            for layer_name in ("lower", "current", "upper"):
                grid = tile_map.layers[layer_name]
                assert len(grid) == tile_map.height
                assert all(len(row) == tile_map.width for row in grid)
                assert grid[0][0].get_size() == (32, 32)
            assert all(0 <= x < tile_map.width and 0 <= y < tile_map.height
                       for x, y in tile_map.blocked)
            assert tile_map.start not in tile_map.blocked

        assert game.pos == list(game.tile_maps["home"].start)

        world = game.tile_maps["world"]
        assert game.map_view == "world"
        assert game.map_view_pos == list(world.start)
        assert world.size == (120, 120)
        assert world.start == (26 + game.tile_maps["home"].start[0],
                               64 + game.tile_maps["home"].start[1])
        assert (0, 0) in world.blocked
        assert world.start not in world.blocked

        for index, name in enumerate(game.MAP_VIEW_ORDER):
            game.switch_map_view(index)
            assert game.map_view == name
            assert game.map_view_pos == list(game.tile_maps[name].start)
    finally:
        game.serial.close()
        pygame.quit()


def test_npc_collision_and_step_events():
    game = Adventure(None)
    try:
        game.map_view = None
        father = tuple(game.NPC_POS["home"])
        game.pos[:] = [father[0], father[1] + 1]
        game.facing = "up"
        game.move(1)
        assert game.step is None
        assert tuple(game.pos) != father
        game.command(5)
        assert game.father_done and game.dialogue

        game.dialogue = []
        game.scene = "route"
        game.pos[:] = [11, 15]
        game.move(1)
        for _ in range(4):
            game.update_movement()
        assert game.dialogue_source == "step"
        assert game.dialogue
        assert ("route", (11, 14)) in game.triggered_step_events
    finally:
        game.serial.close()
        pygame.quit()


def test_battle_assets_and_sensor_moves():
    game = Adventure(None)
    try:
        game.map_view = None
        game.start_battle()
        assert game.scene == "battle"
        assert game.enemy_battle is not None
        assert game.battle_ui["fight"] is not None
        assert all(game.battle_effect_frames[name]
                   for name in ("synthesis", "solar", "heavy", "weather"))

        game.light = 0
        game.use_move(1)
        low_light_damage = 100 - game.enemy_hp
        assert low_light_damage == 22
        assert game.battle_effect and game.battle_effect["name"] == "solar"
        for _ in range(32):
            game.update_battle_effect()
        assert game.battle_effect is None

        game.enemy_hp = 100
        game.light = 1023
        game.use_move(1)
        assert 100 - game.enemy_hp == 68
        game.heavy_ready = True
        game.vibration_count = 3
        game.use_move(2)
        assert not game.heavy_ready
        assert game.battle_effect["name"] == "heavy"
        game.draw_battle()
    finally:
        game.serial.close()
        pygame.quit()


def test_atomic_grid_movement_and_camera():
    game = Adventure(None)
    try:
        assert game.screen.get_size() == (480, 320)
        assert game.display.get_size() == (960, 640)
        assert set(game.player_frames) == {"down", "left", "right", "up"}
        assert all(frame.get_size() == (32, 32)
                   for frames in game.player_frames.values() for frame in frames)

        game.switch_map_view(1)
        tile_map = game.tile_maps[game.map_view]
        directions = ((1, 0, -1), (2, 0, 1), (3, -1, 0), (4, 1, 0))
        command = next(
            command for command, dx, dy in directions
            if (game.map_view_pos[0] + dx, game.map_view_pos[1] + dy) not in tile_map.blocked
            and 0 <= game.map_view_pos[0] + dx < tile_map.width
            and 0 <= game.map_view_pos[1] + dy < tile_map.height
        )
        origin = tuple(game.map_view_pos)
        game.command(command)
        assert game.step is not None
        assert tuple(game.map_view_pos) == origin
        initial_facing = game.facing
        target = game.step["to"]

        game.command(1 if command != 1 else 4)
        assert game.facing == initial_facing
        assert game.step["to"] == target
        for _ in range(3):
            game.update_movement()
            assert tuple(game.map_view_pos) == origin
        game.update_movement()
        assert tuple(game.map_view_pos) == target
        assert game.step is None

        game.switch_map_view(2)
        tile_map = game.tile_maps[game.map_view]
        blocked_origin, blocked_command = next(
            ((x, y), command)
            for y in range(tile_map.height)
            for x in range(tile_map.width)
            if (x, y) not in tile_map.blocked
            for command, dx, dy in directions
            if (x + dx, y + dy) in tile_map.blocked
        )
        game.map_view_pos[:] = blocked_origin
        game.command(blocked_command)
        assert game.step is None
        assert tuple(game.map_view_pos) == blocked_origin

        world = game.tile_maps["world"]
        assert game.map_camera(world, (0, 0))[:2] == (0, 0)
        assert game.map_camera(world, (119, 119))[:2] == (3360, 3520)
    finally:
        game.serial.close()
        pygame.quit()


def test_breakable_cave_rocks():
    game = Adventure(None)
    try:
        game.switch_map_view(1)
        tile_map = game.tile_maps[game.map_view]
        directions = {
            "up": (0, -1), "down": (0, 1),
            "left": (-1, 0), "right": (1, 0),
        }
        target, player, facing = next(
            (target, (target[0] - dx, target[1] - dy), facing)
            for target in sorted(tile_map.blocked)
            if game.upper_tile_exists(tile_map, target)
            for facing, (dx, dy) in directions.items()
            if 0 <= target[0] - dx < tile_map.width
            and 0 <= target[1] - dy < tile_map.height
            and (target[0] - dx, target[1] - dy) not in tile_map.blocked
        )
        game.map_view_pos[:] = player
        game.facing = facing
        assert game.is_breakable_rock(tile_map, target)
        assert game.use_field_heavy_slam()
        assert len(game.rock_break_frames) == 16
        assert all(frame.get_size() == (32, 32) for frame in game.rock_break_frames)
        assert all(frame.get_size() == (32, 32)
                   for frames in game.attack_frames.values() for frame in frames)

        origin = tuple(game.map_view_pos)
        game.command(1)
        assert tuple(game.map_view_pos) == origin
        for _ in range(10):
            if target not in tile_map.blocked:
                break
            game.update_field_attack()
        assert not game.upper_tile_exists(tile_map, target)
        assert target not in tile_map.blocked
        for _ in range(64):
            if not game.field_attack:
                break
            game.update_field_attack()
        assert game.field_attack is None

        ordinary_wall, player, facing = next(
            (target, (target[0] - dx, target[1] - dy), facing)
            for target in sorted(tile_map.blocked)
            if not game.upper_tile_exists(tile_map, target)
            for facing, (dx, dy) in directions.items()
            if 0 <= target[0] - dx < tile_map.width
            and 0 <= target[1] - dy < tile_map.height
            and (target[0] - dx, target[1] - dy) not in tile_map.blocked
        )
        game.map_view_pos[:] = player
        game.facing = facing
        assert not game.use_field_heavy_slam()
        assert ordinary_wall in tile_map.blocked
        assert game.field_attack is None

        game.switch_map_view(2)
        game.switch_map_view(1)
        assert target not in game.tile_maps["grancave"].blocked
        assert not game.upper_tile_exists(game.tile_maps["grancave"], target)
    finally:
        game.serial.close()
        pygame.quit()


def test_bidirectional_warps():
    game = Adventure(None)
    try:
        assert len(game.WARPS) == 12
        game.map_view = "world"
        game.map_view_pos[:] = (40, 10)
        game.command(4)
        assert game.step is not None
        for _ in range(4):
            game.update_movement()
        assert game.map_view == "grancave"
        assert tuple(game.map_view_pos) == (25, 10)

        for source_map, source, target_map, target in game.WARPS:
            source_tile_map = game.tile_maps[source_map]
            target_tile_map = game.tile_maps[target_map]
            assert 0 <= source[0] < source_tile_map.width
            assert 0 <= source[1] < source_tile_map.height
            assert source not in source_tile_map.blocked
            assert 0 <= target[0] < target_tile_map.width
            assert 0 <= target[1] < target_tile_map.height
            assert target not in target_tile_map.blocked

            game.map_view = source_map
            game.map_view_pos[:] = source
            game.warp_fade_frames = 0
            game._map_camera = (99, 99, 99, 99)
            assert game.trigger_warp()
            assert game.map_view == target_map
            assert tuple(game.map_view_pos) == target
            assert game.warp_fade_frames > 0
            assert not hasattr(game, "_map_camera")

        locked_position = tuple(game.map_view_pos)
        game.command(1)
        assert tuple(game.map_view_pos) == locked_position
        for _ in range(12):
            game.update_warp_fade()
        assert game.warp_fade_frames == 0

        start = ("world", game.tile_maps["world"].start)
        queue = deque([start])
        reachable = {start}
        warp_destinations = {
            (source_map, source): (target_map, target)
            for source_map, source, target_map, target in game.WARPS
        }
        while queue:
            map_name, (x, y) = queue.popleft()
            candidates = []
            destination = warp_destinations.get((map_name, (x, y)))
            if destination:
                candidates.append(destination)
            candidates.extend(
                (map_name, (x + dx, y + dy))
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))
            )
            for target_map_name, point in candidates:
                tile_map = game.tile_maps[target_map_name]
                if not (0 <= point[0] < tile_map.width and 0 <= point[1] < tile_map.height):
                    continue
                if point in tile_map.blocked and not game.is_breakable_rock(tile_map, point):
                    continue
                state = (target_map_name, point)
                if state not in reachable:
                    reachable.add(state)
                    queue.append(state)

        assert {map_name for map_name, _point in reachable} == set(game.MAP_VIEW_ORDER)
        assert all((source_map, source) in reachable
                   for source_map, source, _target_map, _target in game.WARPS)
    finally:
        game.serial.close()
        pygame.quit()


def test_ordered_map_event_dialogue_battle_and_once():
    game = Adventure(None)
    try:
        event = {
            "id": "runtime_test",
            "name": "运行时事件测试",
            "map": "world",
            "position": [10, 10],
            "icon": "jirachi_sleep_1.png",
            "once": True,
            "steps": [
                {"type": "dialogue", "preload": "jirachi_right.png", "speaker": "基拉祈", "text": "第一句"},
                {"type": "battle", "battle_id": "placeholder"},
                {"type": "dialogue", "preload": "no_portrait_center.png", "speaker": "", "text": "战斗结束"},
            ],
        }
        game.map_events = [event]
        game.map_event_index = {("world", (10, 10)): event}
        game.map_view = "world"
        game.map_view_pos[:] = (10, 10)

        assert game.trigger_map_event()
        assert game.dialogue_source == "map_event"
        assert game.dialogue_preload == "jirachi_right.png"
        assert game.load_dialogue_preload(game.dialogue_preload) is not None
        assert game.load_map_event_icon(event["icon"]) is not None

        game.update_dialogue_reveal()
        assert game.dialogue_reveal == 0
        game.update_dialogue_reveal()
        assert game.dialogue_reveal == 1
        game.command(5)
        assert game.dialogue_reveal == len(game.dialogue[0])
        assert game.active_map_event_step == 0
        game.command(5)
        assert game.scene == "battle"
        assert game.event_battle_active

        game.battle_lost = True
        game.command(5)
        assert game.map_view == "world"
        assert tuple(game.map_view_pos) == (10, 10)
        assert game.active_map_event_step == 0
        assert game.dialogue_preload == "jirachi_right.png"

        game.command(5)
        game.command(5)
        assert game.scene == "battle"
        game.battle_won = True
        game.battle_lost = False
        game.command(5)
        assert game.map_view is None
        assert game.scene == "battle"
        assert game.active_map_event_step == 2
        assert game.dialogue_preload == "no_portrait_center.png"

        game.command(5)
        game.command(5)
        assert game.active_map_event is None
        assert game.map_view == "world"
        assert tuple(game.map_view_pos) == (10, 10)
        assert "runtime_test" in game.completed_map_events
        assert not game.trigger_map_event()

        game.reset()
        assert not game.completed_map_events
    finally:
        game.serial.close()
        pygame.quit()


if __name__ == "__main__":
    test_story_path()
    test_tile_map_loading_and_view_switching()
    test_npc_collision_and_step_events()
    test_battle_assets_and_sensor_moves()
    test_atomic_grid_movement_and_camera()
    test_breakable_cave_rocks()
    test_bidirectional_warps()
    test_ordered_map_event_dialogue_battle_and_once()
    print("story path ok")
