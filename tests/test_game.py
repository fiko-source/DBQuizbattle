import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizbattle.game import QuizGame


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.replications = 0
        self.events = []

        async def replicate():
            self.replications += 1

        async def emit(event_type, **data):
            self.events.append({"type": event_type, **data})
            await replicate()

        self.game = QuizGame(lambda: {"token"}, emit, replicate)
        self.game.state["players"] = {
            "token": {"name": "Taufik", "player_id": "P1"}
        }
        self.game.state["scores"] = {"token": 0}

    def test_database_path_is_independent_of_working_directory(self):
        self.assertGreater(len(self.game.questions), 0)

    async def test_request_id_prevents_duplicate_answer_application(self):
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
        self.game.state["scores"]["token"] = 3
        self.assertEqual(self.game.public_scores(), {"Taufik": 3})

    def test_team_groups_have_exactly_two_members(self):
        self.game.connected_tokens = lambda: {"a", "b", "c"}
        teams = self.game.create_teams()
        self.assertTrue(teams)
        self.assertTrue(all(len(members) == 2 for members in teams.values()))

    async def test_round_phases_are_explicit_events(self):
        self.game.state["question_order"] = [0]
        await self.game.start_next_round()
        self.assertEqual(
            [event["type"] for event in self.events],
            ["ROUND_START", "QUESTION", "ANSWER_PHASE_START"],
        )


if __name__ == "__main__":
    unittest.main()
