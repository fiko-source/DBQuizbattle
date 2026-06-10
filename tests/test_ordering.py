import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.client_ordering import OrderedEventBuffer


class OrderedEventBufferTests(unittest.TestCase):
    def test_gap_is_held_back_and_requested(self):
        buffer = OrderedEventBuffer()
        delivered, missing = buffer.receive({"seq": 2, "type": "RESULT"})
        self.assertEqual(delivered, [])
        self.assertEqual(missing, (1, 1))

        delivered, missing = buffer.receive({"seq": 1, "type": "QUESTION"})
        self.assertEqual([event["seq"] for event in delivered], [1, 2])
        self.assertIsNone(missing)
        self.assertEqual(buffer.last_sequence, 2)

    def test_duplicate_is_not_delivered_twice(self):
        buffer = OrderedEventBuffer(last_sequence=3)
        delivered, missing = buffer.receive({"seq": 3, "type": "QUESTION"})
        self.assertEqual(delivered, [])
        self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
