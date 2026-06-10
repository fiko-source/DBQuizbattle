import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.protocol import frame_message, read_frame


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_message_is_length_framed(self):
        reader = asyncio.StreamReader()
        reader.feed_data(frame_message({"type": "TEST", "value": "ä"}))
        reader.feed_eof()
        self.assertEqual(
            await read_frame(reader),
            {"type": "TEST", "value": "ä"},
        )


if __name__ == "__main__":
    unittest.main()
