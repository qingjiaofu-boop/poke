"""Regression checks for the Essentials-style STC-B story path."""
import os

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
        game.pos[:] = [1, 2]
        game.command(5)
        assert game.father_done and game.dialogue
        advance_dialogue(game)

        game.scene = "friend"
        game.pos[:] = [2, 6]
        game.command(5)
        assert game.friend_met and game.dialogue
        advance_dialogue(game)
        assert game.scene == "battle"

        game.enemy_hp = 1
        game.move_cursor = 1
        game.command(5)
        assert game.battle_won
        game.command(5)
        assert game.scene == "route"

        game.scene = "cave3"
        game.pos[:] = [6, 5]
        game.command(9)
        assert game.rock_broken
    finally:
        game.serial.close()
        pygame.quit()


if __name__ == "__main__":
    test_story_path()
    print("story path ok")
