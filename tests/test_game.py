"""Tests fuer Spiellogik, Deduplizierung und Rundenereignisse."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.game import QuizGame


class GameTests(unittest.IsolatedAsyncioTestCase):
    """Pruefe die Spiellogik ohne laufenden WebSocket-Server."""

    async def asyncSetUp(self):
        """Erzeuge vor jedem Test ein Spiel mit aufgezeichneten Callbacks."""
        self.replications = 0
        self.events = []

        async def replicate():
            """Zaehle simulierte Replikationsaufrufe."""
            self.replications += 1

        async def emit(event_type, **data):
            """Speichere simulierte Spielereignisse in ihrer Reihenfolge."""
            self.events.append({"type": event_type, **data})
            await replicate()

        self.game = QuizGame(lambda: {"token"}, emit, replicate)
        self.game.state["players"] = {
            "token": {"name": "Taufik", "player_id": "P1"}
        }
        self.game.state["scores"] = {"token": 0}

    def test_database_path_is_independent_of_working_directory(self):
        """Fragen werden ueber den Projektpfad und nicht das Terminal gefunden."""
        self.assertGreater(len(self.game.questions), 0)

    async def test_request_id_prevents_duplicate_answer_application(self):
        """Dieselbe request_id darf eine Antwort nicht doppelt anwenden."""
        self.game.state["phase"] = "question"
        message = {
            "type": "ANSWER",
            "answer": "11",
            "request_id": "request-1",
        }
        first = await self.game.handle_action("token", message)
        second = await self.game.handle_action("token", message)
        self.assertEqual(first, "Antwort gespeichert.")
        self.assertEqual(second, "Antwort gespeichert.")
        self.assertEqual(self.game.state["answers"], {"token": "11"})
        self.assertIn("request-1", self.game.state["processed_requests"])

    def test_public_scores_do_not_expose_tokens(self):
        """Oeffentliche Punktestaende enthalten Namen statt Sitzungstokens."""
        self.game.state["scores"]["token"] = 3
        self.assertEqual(self.game.public_scores(), {"Taufik": 3})

    def test_team_groups_have_exactly_two_members(self):
        """Erzeugte Teams bestehen immer aus genau zwei Personen."""
        self.game.connected_tokens = lambda: {"a", "b", "c"}
        teams = self.game.create_teams()
        self.assertTrue(teams)
        self.assertTrue(all(len(members) == 2 for members in teams.values()))

    async def test_round_phases_are_explicit_events(self):
        """Ein Rundenstart erzeugt die erwarteten getrennten Phasenereignisse."""
        self.game.state["current_category"] = "Fußball"
        self.game.state["category_questions"] = {"Fußball": [0]}
        await self.game.start_next_round()
        self.assertEqual(
            [event["type"] for event in self.events],
            ["ROUND_START", "QUESTION", "ANSWER_PHASE_START"],
        )
        self.assertEqual(self.events[1]["category"], "Fußball")

    async def test_category_selection_names_current_chooser(self):
        """Die Kategorieauswahl nennt den Spieler, der auswaehlen darf."""
        await self.game.start_category_selection()
        self.assertEqual(self.game.state["phase"], "category_select")
        self.assertEqual(self.game.state["category_chooser_token"], "token")
        self.assertEqual(self.events[-1]["type"], "CATEGORY_SELECTION")
        self.assertIn("Allgemeinwissen", self.events[-1]["categories"])
        self.assertEqual(self.events[-1]["chooser_id"], "P1")

    async def test_only_current_chooser_can_select_category(self):
        """Nur der ausgewaehlte Spieler darf die naechste Kategorie setzen."""
        self.game.state["players"]["other"] = {
            "name": "Musab",
            "player_id": "P2",
        }
        self.game.state["scores"]["other"] = 0
        self.game.state["phase"] = "category_select"
        self.game.state["category_chooser_token"] = "token"
        status = await self.game.handle_action(
            "other",
            {
                "type": "CATEGORY_CHOICE",
                "category": "Allgemeinwissen",
                "request_id": "choice-1",
            },
        )
        self.assertEqual(
            status,
            "Du bist aktuell nicht mit der Kategorieauswahl dran.",
        )
        self.assertIsNone(self.game.state["current_category"])

    async def test_category_choice_starts_question_block(self):
        """Eine gueltige Kategorieauswahl startet die naechste Frage."""
        self.game.state["phase"] = "category_select"
        self.game.state["category_chooser_token"] = "token"
        status = await self.game.handle_action(
            "token",
            {
                "type": "CATEGORY_CHOICE",
                "category": "Allgemeinwissen",
                "request_id": "choice-2",
            },
        )
        self.assertEqual(status, "Kategorie gewählt: Allgemeinwissen")
        self.assertEqual(self.game.state["phase"], "question")
        self.assertEqual(self.game.state["current_category"], "Allgemeinwissen")
        self.assertEqual(self.game.state["category_round_count"], 1)
        self.assertIn("CATEGORY_SELECTED", [event["type"] for event in self.events])

    async def test_game_reset_starts_fresh_game_but_keeps_player(self):
        """Nach GAME_OVER startet ein neues Spiel mit bekannten Spielern neu."""
        self.game.state.update(
            {
                "phase": "game_over",
                "round": 5,
                "question_order": [0],
                "scores": {"token": 3},
                "answers": {"token": "old"},
                "processed_requests": {"request-1": "Antwort gespeichert."},
                "sequence": 9,
                "events": [{"type": "GAME_OVER", "seq": 9}],
            }
        )

        await self.game.reset_for_new_game()

        self.assertEqual(self.game.state["phase"], "waiting")
        self.assertEqual(self.game.state["round"], 0)
        self.assertEqual(self.game.state["scores"], {"token": 0})
        self.assertEqual(self.game.state["answers"], {})
        self.assertEqual(self.game.state["processed_requests"], {})
        self.assertIn("token", self.game.state["players"])
        self.assertEqual(self.events[-1]["type"], "GAME_RESET")
        self.assertEqual(self.events[-1]["scores"], {"P1": 0})


if __name__ == "__main__":
    unittest.main()
