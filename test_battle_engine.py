import unittest

from battle_engine import Battle, Move, Pokemon, calculate_damage, load_move, load_species
from protagonist_moves import SensorSnapshot, protagonist_move


class BattleEngineTests(unittest.TestCase):
    def setUp(self):
        self.player = Pokemon(load_species("FERROTHORN"), level=50)
        self.foe = Pokemon(load_species("FERROSEED"), level=20)

    def test_default_is_six_v(self):
        self.assertEqual(self.player.ivs, {name: 31 for name in self.player.ivs})
        self.assertEqual(self.player.stats["hp"], 149)
        self.assertEqual(self.player.stats["attack"], 114)

    def test_damage_keeps_stab_type_and_random_components(self):
        move = load_move("SOLARBEAM")
        result = calculate_damage(self.player, self.foe, move, random_factor=255)
        self.assertEqual(result.random_factor, 255)
        self.assertEqual(result.stab, 1.5)
        self.assertEqual(result.type_multiplier, 0.25)
        self.assertGreater(result.damage, 0)

    def test_miss_does_not_damage(self):
        move = Move("TEST", "测试", "NORMAL", "Physical", 100, accuracy=50)
        battle = Battle(self.player, self.foe, {move.id: move})
        result = battle.use_player_move("TEST", accuracy_roll=51, critical_roll=1)
        self.assertFalse(result.hit)
        self.assertIsNone(result.damage)
        self.assertEqual(result.defender_hp, self.foe.max_hp)

    def test_critical_is_resolved_by_the_turn(self):
        move = Move("TEST", "测试", "NORMAL", "Physical", 100)
        normal = Battle(Pokemon(load_species("FERROTHORN"), 50), Pokemon(load_species("FERROSEED"), 20), {move.id: move})
        critical = Battle(Pokemon(load_species("FERROTHORN"), 50), Pokemon(load_species("FERROSEED"), 20), {move.id: move})
        normal_result = normal.use_player_move("TEST", random_factor=255, critical_roll=1)
        critical_result = critical.use_player_move("TEST", random_factor=255, critical_roll=0)
        self.assertFalse(normal_result.critical)
        self.assertTrue(critical_result.critical)
        self.assertGreater(critical_result.damage.damage, normal_result.damage.damage)

    def test_sensor_move_is_runtime_calculated(self):
        sensors = SensorSnapshot(light=1023, temperature=32, vibration_count=3, heavy_ready=True)
        solar = protagonist_move("STC_SOLARBEAM", sensors)
        weather = protagonist_move("STC_WEATHERBALL", sensors)
        heavy = protagonist_move("STC_HEAVYSLAM", sensors)
        self.assertEqual(solar.power, 120)
        self.assertEqual(weather.type, "FIRE")
        self.assertEqual(weather.power, 100)
        self.assertEqual(heavy.power, 92)


if __name__ == "__main__":
    unittest.main()
