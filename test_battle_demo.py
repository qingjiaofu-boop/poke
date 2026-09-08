import random
import unittest

from battle_demo import (
    ENCOUNTERS,
    FOE_BOX_RECT,
    MESSAGE_POS,
    MOVE_INFO_POS,
    MOVE_LIST_POS,
    PLAYER_BOX_RECT,
    STC_VIBRATION_COMMAND,
    EncounterBattleRules,
)


class EncounterBattleRulesTests(unittest.TestCase):
    def test_encounter_specs_match_source_files(self):
        expected = {
            "zubat": (90, 20, 30, (18, 28, 26), "威力：70"),
            "aron": (176, 40, 30, (30, 35, 39), "威力：70"),
            "sableye": (148, 21, 20, (43, 58, 70), "威力：40"),
        }
        for key, values in expected.items():
            encounter = ENCOUNTERS[key]
            foe_hp, solar_damage, heal_percent, foe_damage, power_label = values
            self.assertEqual(encounter.enemy_max_hp, foe_hp)
            self.assertEqual(encounter.player_moves[0].damage, solar_damage)
            self.assertEqual(encounter.player_moves[0].value_label, power_label)
            self.assertEqual(encounter.player_moves[1].heal_percent, heal_percent)
            self.assertEqual(tuple(move.damage for move in encounter.foe_moves), foe_damage)

    def test_each_encounter_starts_with_correct_hp(self):
        for key, encounter in ENCOUNTERS.items():
            battle = EncounterBattleRules(key)
            self.assertEqual((battle.player_hp, battle.foe_hp), (149, encounter.enemy_max_hp))

    def test_player_moves_apply_each_encounters_values(self):
        for key, encounter in ENCOUNTERS.items():
            battle = EncounterBattleRules(key)
            self.assertEqual(battle.use_player_move(encounter.player_moves[0]), encounter.player_moves[0].damage)
            battle.player_hp = 70
            expected_heal = min(149 - 70, round(149 * encounter.player_moves[1].heal_percent / 100))
            self.assertEqual(battle.use_player_move(encounter.player_moves[1]), expected_heal)

    def test_foe_moves_apply_each_encounters_values(self):
        for key, encounter in ENCOUNTERS.items():
            for move in encounter.foe_moves:
                battle = EncounterBattleRules(key)
                self.assertEqual(battle.use_foe_move(move), move.damage)
                self.assertEqual(battle.player_hp, 149 - move.damage)

    def test_seeded_foe_selection_is_repeatable(self):
        for encounter in ENCOUNTERS.values():
            first = random.Random(17).choice(encounter.foe_moves)
            second = random.Random(17).choice(encounter.foe_moves)
            self.assertEqual(first, second)

    def test_sableye_has_heavy_slam_vibration_move(self):
        move = ENCOUNTERS["sableye"].player_moves[2]
        self.assertEqual((move.name, move.damage), ("重磅冲撞", 75))
        self.assertEqual(move.info_lines, ("双方体重相差越大", "威力越高"))
        self.assertEqual(move.trigger, "vibration")
        self.assertEqual(STC_VIBRATION_COMMAND, 0x09)

    def test_sableye_has_both_cave_tutorial_notes(self):
        notes = ENCOUNTERS["sableye"].opening_notes
        self.assertEqual(len(notes), 2)
        self.assertIn("光线较弱", notes[0])
        self.assertIn("敲击小板", notes[1])
        self.assertFalse(ENCOUNTERS["aron"].opening_notes)

    def test_primary_layout_uses_2x_pixel_coordinates(self):
        layouts = (FOE_BOX_RECT, PLAYER_BOX_RECT, MESSAGE_POS, MOVE_LIST_POS, MOVE_INFO_POS)
        self.assertTrue(all(value % 2 == 0 for layout in layouts for value in layout))


if __name__ == "__main__":
    unittest.main()
