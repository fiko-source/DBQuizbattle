"""Tests fuer Erzeugung und Speicherung der Server-UUID."""

import sys
import tempfile
import unittest
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.identity import load_or_create_uuid, normalize_uuid


class IdentityTests(unittest.TestCase):
    """Pruefe stabile und gueltige Serveridentitaeten."""

    def test_generated_uuid_is_reused(self):
        """Ein Neustart mit derselben Datei muss dieselbe UUID verwenden."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server.uuid"
            first = load_or_create_uuid(path)
            second = load_or_create_uuid(path)

        self.assertEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)

    def test_invalid_uuid_is_rejected(self):
        """Ein ungueltiger UUID-Text darf nicht als Serveridentitaet gelten."""
        with self.assertRaises(ValueError):
            normalize_uuid("keine-uuid")
