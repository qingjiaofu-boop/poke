from scripted_battle import GrotleTutorial


def advance_to_first_move(tutorial):
    tutorial.confirm()
    tutorial.confirm()
    action = tutorial.confirm()
    assert action and action.target == "player"
    tutorial.complete_action()
    tutorial.confirm()
    tutorial.confirm()


def test_tutorial_unlock_order_and_sensor_ranges():
    tutorial = GrotleTutorial()
    advance_to_first_move(tutorial)
    assert tutorial.stage == "require_solar"
    assert tutorial.player_hp == 67
    assert tutorial.available_moves == ("solar_beam",)

    action = tutorial.choose_move("solar_beam", 0)
    assert action.amount == 34
    tutorial.complete_action()
    assert tutorial.stage == "praise"

    tutorial.confirm()
    tutorial.confirm()
    action = tutorial.confirm()
    assert action.amount == 33
    tutorial.complete_action()
    tutorial.confirm()
    tutorial.confirm()
    assert tutorial.stage == "require_synthesis"

    action = tutorial.choose_move("solar_beam", 1023)
    assert action is None
    assert "光合作用" in tutorial.message
    action = tutorial.choose_move("synthesis", 1023)
    assert action.amount == 60
    tutorial.complete_action()
    tutorial.confirm()
    assert tutorial.stage == "free_battle"


def test_free_battle_can_win_and_reports_outcome():
    tutorial = GrotleTutorial()
    tutorial.stage = "free_battle"
    tutorial.foe_hp = 55
    action = tutorial.choose_move("solar_beam", 1023)
    assert action.amount == 55
    tutorial.complete_action()
    assert tutorial.outcome == "won"


def test_free_battle_can_lose_and_reset():
    tutorial = GrotleTutorial()
    tutorial.stage = "enemy_free_announce"
    tutorial.player_hp = 20
    action = tutorial.confirm()
    assert action.amount == 20
    tutorial.complete_action()
    assert tutorial.outcome == "lost"
    tutorial.reset()
    assert tutorial.stage == "intro_absorb"
    assert tutorial.player_hp == tutorial.player_max_hp


if __name__ == "__main__":
    test_tutorial_unlock_order_and_sensor_ranges()
    test_free_battle_can_win_and_reports_outcome()
    test_free_battle_can_lose_and_reset()
    print("scripted battle ok")
