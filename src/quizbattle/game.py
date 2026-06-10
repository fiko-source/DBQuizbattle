import asyncio
import random
import time
import uuid

from tinydb import TinyDB

from .settings import MIN_PLAYERS, PROJECT_DIR, RESULT_TIME, ROUND_TIME


def load_questions():
    database = TinyDB(PROJECT_DIR / "tinydb.json")
    try:
        return database.all()
    finally:
        database.close()


def initial_state():
    return {
        "version": 0,
        "phase": "waiting",
        "round": 0,
        "question_order": [],
        "question": None,
        "deadline": 0,
        "team_round": False,
        "teams": {},
        "answers": {},
        "team_answers": {},
        "players": {},
        "scores": {},
        "processed_requests": {},
        "sequence": 0,
        "events": [],
    }


class QuizGame:
    def __init__(self, connected_tokens, emit_event, replicate_state):
        self.connected_tokens = connected_tokens
        self.emit_event = emit_event
        self.replicate_state = replicate_state
        self.questions = load_questions()
        self.state = initial_state()

    def replace_state(self, state):
        self.state = state

    def mark_changed(self):
        self.state["version"] = self.state.get("version", 0) + 1

    async def add_or_resume_player(self, requested_token, name):
        if requested_token in self.state["players"]:
            return requested_token

        token = uuid.uuid4().hex
        player_number = len(self.state["players"]) + 1
        self.state["players"][token] = {
            "name": name or f"Player {player_number}",
            "player_id": f"P{player_number}",
        }
        self.state["scores"][token] = 0
        self.mark_changed()
        await self.replicate_state()
        return token

    async def handle_action(self, token, message):
        request_id = message.get("request_id")
        processed = self.state["processed_requests"]
        if request_id and request_id in processed:
            return processed[request_id]

        if self.state["phase"] != "question":
            status = "Aktuell läuft keine Frage."
            await self.remember_request(request_id, status)
            return status

        message_type = message.get("type")
        answer = str(message.get("answer", "")).strip()

        if (
            message_type == "ANSWER"
            and answer
            and (
                not self.state["team_round"]
                or self.team_for(token) is None
            )
        ):
            if token in self.state["answers"]:
                status = "Antwort wurde bereits gespeichert."
                await self.remember_request(request_id, status)
                return status
            self.state["answers"][token] = answer
            self.mark_changed()
            status = "Antwort gespeichert."
            await self.remember_request(request_id, status, replicate=False)
            await self.replicate_state()
            return status

        if message_type == "TEAM_ANSWER" and answer and self.state["team_round"]:
            team_id = self.team_for(token)
            if not team_id:
                status = "Du bist keinem Team zugeordnet."
                await self.remember_request(request_id, status)
                return status
            self.state["team_answers"][team_id] = answer
            self.mark_changed()
            status = "Gemeinsame Teamantwort gespeichert."
            await self.remember_request(request_id, status, replicate=False)
            await self.emit_event(
                "TEAM_ANSWERED",
                team=team_id,
                player=self.state["players"][token]["name"],
            )
            return status

        if message_type == "TEAM_CHAT" and self.state["team_round"]:
            team_id = self.team_for(token)
            text = str(message.get("message", "")).strip()[:200]
            if team_id and text:
                status = "Teamnachricht gesendet."
                await self.remember_request(request_id, status, replicate=False)
                await self.emit_event(
                    "TEAM_MESSAGE",
                    team=team_id,
                    player=self.state["players"][token]["name"],
                    message=text,
                )
                return status

        return None

    async def remember_request(self, request_id, status, replicate=True):
        if not request_id:
            return
        self.state["processed_requests"][request_id] = status
        if len(self.state["processed_requests"]) > 1000:
            oldest = next(iter(self.state["processed_requests"]))
            self.state["processed_requests"].pop(oldest)
        self.mark_changed()
        if replicate:
            await self.replicate_state()

    def team_for(self, token):
        for team_id, members in self.state["teams"].items():
            if token in members:
                return team_id
        return None

    async def run(self, is_leader):
        while is_leader():
            phase = self.state["phase"]
            if phase == "waiting":
                if len(self.connected_tokens()) >= MIN_PLAYERS:
                    if not self.state["question_order"]:
                        order = list(range(len(self.questions)))
                        random.shuffle(order)
                        self.state["question_order"] = order
                        self.mark_changed()
                    await self.start_next_round()
                else:
                    await asyncio.sleep(0.5)
            elif phase == "question":
                await asyncio.sleep(max(0, self.state["deadline"] - time.time()))
                if is_leader() and self.state["phase"] == "question":
                    await self.evaluate_round()
            elif phase == "result":
                await asyncio.sleep(max(0, self.state["deadline"] - time.time()))
                if is_leader() and self.state["phase"] == "result":
                    await self.start_next_round()
            else:
                await asyncio.sleep(1)

    async def start_next_round(self):
        round_number = self.state["round"] + 1
        order = self.state["question_order"]
        if round_number > len(order):
            self.state["phase"] = "game_over"
            self.mark_changed()
            await self.emit_event(
                "GAME_OVER",
                scores=self.public_scores(),
                message="Spiel beendet.",
            )
            return

        question = self.questions[order[round_number - 1]]
        team_round = round_number % 3 == 0
        self.state.update(
            {
                "phase": "question",
                "round": round_number,
                "question": question,
                "deadline": time.time() + ROUND_TIME,
                "team_round": team_round,
                "teams": self.create_teams() if team_round else {},
                "answers": {},
                "team_answers": {},
            }
        )
        self.mark_changed()
        if round_number > 1:
            await self.emit_event("NEXT_ROUND", round=round_number)
        await self.emit_event("ROUND_START", round=round_number)
        await self.emit_event(
            "QUESTION",
            round=round_number,
            question=question["frage"],
            duration=ROUND_TIME,
            deadline=self.state["deadline"],
            team_round=team_round,
            teams=self.public_teams(),
        )
        await self.emit_event(
            "ANSWER_PHASE_START",
            round=round_number,
            deadline=self.state["deadline"],
            duration=ROUND_TIME,
        )

    def create_teams(self):
        players = list(self.connected_tokens())
        random.shuffle(players)
        return {
            f"Team {index // 2 + 1}": players[index : index + 2]
            for index in range(0, len(players) - 1, 2)
        }

    def public_teams(self):
        return {
            team: [
                {
                    "player_id": self.state["players"][token]["player_id"],
                    "name": self.state["players"][token]["name"],
                }
                for token in members
            ]
            for team, members in self.state["teams"].items()
        }

    def public_scores(self):
        return {
            self.state["players"][token]["name"]: score
            for token, score in self.state["scores"].items()
        }

    async def evaluate_round(self):
        correct = self.state["question"]["antwort"].strip().casefold()
        results = {}

        if self.state["team_round"]:
            team_members = set()
            for team, members in self.state["teams"].items():
                team_members.update(members)
                answer = self.state["team_answers"].get(team)
                is_correct = bool(answer) and answer.strip().casefold() == correct
                for token in members:
                    if is_correct:
                        self.state["scores"][token] = (
                            self.state["scores"].get(token, 0) + 1
                        )
                    results[token] = {"answer": answer, "correct": is_correct}
            for token in set(self.state["players"]) - team_members:
                answer = self.state["answers"].get(token)
                is_correct = bool(answer) and answer.strip().casefold() == correct
                if is_correct:
                    self.state["scores"][token] = (
                        self.state["scores"].get(token, 0) + 1
                    )
                results[token] = {"answer": answer, "correct": is_correct}
        else:
            for token in self.state["players"]:
                answer = self.state["answers"].get(token)
                is_correct = bool(answer) and answer.strip().casefold() == correct
                if is_correct:
                    self.state["scores"][token] = (
                        self.state["scores"].get(token, 0) + 1
                    )
                results[token] = {"answer": answer, "correct": is_correct}

        self.state["phase"] = "result"
        self.state["deadline"] = time.time() + RESULT_TIME
        self.mark_changed()
        await self.emit_event(
            "RESULT",
            correct_answer=self.state["question"]["antwort"],
            results={
                self.state["players"][token]["player_id"]: result
                for token, result in results.items()
            },
            scores={
                self.state["players"][token]["player_id"]: score
                for token, score in self.state["scores"].items()
            },
            public_scores=self.public_scores(),
            next_round_in=RESULT_TIME,
        )
