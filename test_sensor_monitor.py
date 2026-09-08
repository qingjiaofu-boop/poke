import unittest

from sensor_monitor import ProtocolParser
from essentials_adventure import STCProtocolParser


class ProtocolParserTests(unittest.TestCase):
    def test_sensor_packets_preserve_raw_adc_values(self):
        parser = ProtocolParser()
        events = parser.feed(bytes((0x40, 0x03, 0xE8, 0x41, 0x01, 0x2C)))
        self.assertEqual([event.kind for event in events], ["light_raw_adc", "temperature_raw_adc"])
        self.assertEqual([event.value for event in events], [1000, 300])
        self.assertEqual(events[0].raw, bytes((0x40, 0x03, 0xE8)))
        self.assertEqual(events[1].raw, bytes((0x41, 0x01, 0x2C)))

    def test_vibration_and_key_are_not_transformed(self):
        events = ProtocolParser().feed(bytes((0x09, 0x05, 0x06)))
        self.assertEqual([event.kind for event in events], ["vibration", "key", "key"])
        self.assertEqual([event.value for event in events[1:]], [5, 6])

    def test_packet_can_be_split_across_reads(self):
        parser = ProtocolParser()
        self.assertEqual(parser.feed(bytes((0x40, 0x02))), [])
        events = parser.feed(bytes((0x01,)))
        self.assertEqual(events[0].value, 513)

    def test_adventure_parser_keeps_header_values_inside_payload(self):
        parser = STCProtocolParser()
        self.assertEqual(parser.feed(bytes((0x40, 0x40, 0x41))),
                         [("sensor", 0, 0x4041)])
        self.assertEqual(parser.feed(bytes((0x41, 0x40, 0x40))),
                         [("sensor", 1, 0x4040)])


if __name__ == "__main__":
    unittest.main()
