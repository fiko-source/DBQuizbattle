"""Zentrale, replizierbare Spiellogik des QuizBattle-Servers."""

import asyncio
import random
import time
import uuid

from tinydb import TinyDB

from .settings import MIN_PLAYERS, PROJECT_DIR, RESULT_TIME, ROUND_TIME


CATEGORY_BLOCK_SIZE = 5
DEFAULT_CATEGORIES = [
    "Fußball",
    "Politik",
    "Geschichte",
    "Erdkunde (Hauptstädte)",
    "Allgemeinwissen",
]


def load_questions():
    """Lade alle Quizfragen aus der projektlokalen TinyDB-Datenbank."""
    database = TinyDB(PROJECT_DIR / "tinydb.json")
    try:
        return database.all()
    finally:
        database.close()


def initial_state():
    """Erzeuge einen frischen Spielzustand mit allen replizierten Feldern."""
    # Der Zustand besteht nur aus JSON-kompatiblen Werten. Dadurch kann er
    # einfach kopiert, ueber TCP versendet und von einem Backup uebernommen werden.
    return {
        "version": 0,
        "phase": "waiting",
        "round": 0,
        "question_order": [],
        "category_questions": {},
        "current_category": None,
        "category_round_count": 0,
        "category_chooser_index": 0,
        "category_chooser_token": None,
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
    """Verwalte Spieler, Runden, Antworten, Teams und Punktestaende."""

    def __init__(self, connected_tokens, emit_event, replicate_state):
        """Verbinde die Spiellogik ueber Callbacks mit Server und Cluster."""
        self.connected_tokens = connected_tokens
        self.emit_event = emit_event
        self.replicate_state = replicate_state
        self.questions = load_questions()
        self.state = initial_state()

    def replace_state(self, state):
        """Ersetze den lokalen Zustand durch eine Replik des Leaders."""
        self.state = state

    def mark_changed(self):
        """Erhoehe die Version nach jeder inhaltlichen Zustandsaenderung."""
        self.state["version"] = self.state.get("version", 0) + 1

    def categories(self):
        """Gib alle bekannten Kategorien in einer stabilen Reihenfolge zurueck."""
        existing = {question.get("kategorie", "Allgemeinwissen") for question in self.questions}
        preferred = [category for category in DEFAULT_CATEGORIES if category in existing]
        extras = sorted(existing - set(preferred))
        return preferred + extras

    def ensure_category_questions(self):
        """Erzeuge gemischte Frage-Pools pro Kategorie, falls sie fehlen."""
        pools = self.state.get("category_questions") or {}
        if pools:
            return

        pools = {category: [] for category in self.categories()}
        for index, question in enumerate(self.questions):
            category = question.get("kategorie", "Allgemeinwissen")
            pools.setdefault(category, []).append(index)
        for pool in pools.values():
            random.shuffle(pool)
        self.state["category_questions"] = pools
        self.mark_changed()

    def available_categories(self):
        """Zeige Kategorien an, fuer die noch nicht gespielte Fragen existieren."""
        self.ensure_category_questions()
        return [
            category
            for category in self.categories()
            if self.state["category_questions"].get(category)
        ]

    def ordered_player_tokens(self, connected_only=False):
        """Sortiere Spieler stabil nach ihrer sichtbaren Spieler-ID."""
        tokens = list(self.state["players"])
        if connected_only:
            connected = self.connected_tokens()
            tokens = [token for token in tokens if token in connected]
        return sorted(
            tokens,
            key=lambda token: self.state["players"][token]["player_id"],
        )

    def category_chooser(self):
        """Bestimme den Spieler, der die naechste Kategorie auswaehlen darf."""
        tokens = self.ordered_player_tokens(connected_only=True)
        if not tokens:
            tokens = self.ordered_player_tokens()
        if not tokens:
            return None

        chooser_index = self.state.get("category_chooser_index", 0) % len(tokens)
        return tokens[chooser_index]

    async def add_or_resume_player(self, requested_token, name):
        """Setze eine bekannte Sitzung fort oder registriere einen neuen Spieler."""
        # Ein Token bleibt beim Client ueber Reconnects erhalten. Dadurch bekommt
        # derselbe Spieler nach einem Leaderwechsel keinen zweiten Eintrag.
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
        """Pruefe und verarbeite Antwort-, Teamantwort- oder Chataktionen."""
        request_id = message.get("request_id")
        processed = self.state["processed_requests"]
        # Eine erneut gesendete Aktion liefert nur ihr altes Ergebnis. Das macht
        # Wiederholungen nach Paket- oder Verbindungsverlust idempotent.
        if request_id and request_id in processed:
            return processed[request_id]

        if message.get("type") == "CATEGORY_CHOICE":
            return await self.handle_category_choice(token, message)

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
            # In einer Einzelrunde darf jeder Spieler genau eine Antwort abgeben.
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
            # Eine neue Teamantwort ersetzt eine vorherige gemeinsame Antwort;
            # alle Teammitglieder erhalten spaeter dasselbe Ergebnis.
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
            # Chattexte werden begrenzt, bevor sie als geordnetes Ereignis an
            # alle Clients verteilt werden.
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

    async def handle_category_choice(self, token, message):
        """Pruefe die Kategorieauswahl und starte den naechsten Fragenblock."""
        request_id = message.get("request_id")
        if self.state["phase"] != "category_select":
            status = "Aktuell steht keine Kategorieauswahl an."
            await self.remember_request(request_id, status)
            return status

        if token != self.state.get("category_chooser_token"):
            status = "Du bist aktuell nicht mit der Kategorieauswahl dran."
            await self.remember_request(request_id, status)
            return status

        category = str(message.get("category", "")).strip()
        if category not in self.available_categories():
            status = "Diese Kategorie ist nicht verfügbar."
            await self.remember_request(request_id, status)
            return status

        self.state["current_category"] = category
        self.state["category_round_count"] = 0
        self.state["category_chooser_token"] = None
        self.state["category_chooser_index"] = (
            self.state.get("category_chooser_index", 0) + 1
        )
        self.mark_changed()
        status = f"Kategorie gewählt: {category}"
        await self.remember_request(request_id, status, replicate=False)
        chooser = self.state["players"][token]
        await self.emit_event(
            "CATEGORY_SELECTED",
            category=category,
            chooser=chooser["name"],
            chooser_id=chooser["player_id"],
        )
        await self.start_next_round()
        return status

    async def remember_request(self, request_id, status, replicate=True):
        """Merke das Ergebnis einer Aktion fuer deduplizierte Wiederholungen."""
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
        """Finde das Team, in dem ein bestimmter Spielertoken enthalten ist."""
        for team_id, members in self.state["teams"].items():
            if token in members:
                return team_id
        return None

    async def run(self, is_leader):
        """Fuehre als Leader den Zustandsautomaten des Spiels dauerhaft aus."""
        while is_leader():
            phase = self.state["phase"]
            if phase == "waiting":
                if len(self.connected_tokens()) >= MIN_PLAYERS:
                    await self.start_category_selection()
                else:
                    await asyncio.sleep(0.5)
            elif phase == "category_select":
                await asyncio.sleep(0.5)
            elif phase == "question":
                # Gespeicherte absolute Deadlines bleiben auch nach einer
                # Uebernahme durch einen neuen Leader sinnvoll.
                await asyncio.sleep(max(0, self.state["deadline"] - time.time()))
                if is_leader() and self.state["phase"] == "question":
                    await self.evaluate_round()
            elif phase == "result":
                await asyncio.sleep(max(0, self.state["deadline"] - time.time()))
                if is_leader() and self.state["phase"] == "result":
                    await self.start_next_round()
            elif phase == "game_over":
                # Nach einem beendeten Spiel soll der Server nicht dauerhaft im
                # Endzustand bleiben. Die Sequenznummer und Ereignishistorie
                # bleiben erhalten, damit verbundene Clients weiterhin geordnete
                # Events bekommen und ihre ACK/Resend-Logik nicht neu starten muss.
                await asyncio.sleep(RESULT_TIME)
                if is_leader() and self.state["phase"] == "game_over":
                    await self.reset_for_new_game()
            else:
                await asyncio.sleep(1)

    async def reset_for_new_game(self):
        """Setze Runden- und Punktestand fuer ein neues Spiel zurueck."""
        self.state.update(
            {
                "phase": "waiting",
                "round": 0,
                "question_order": [],
                "category_questions": {},
                "current_category": None,
                "category_round_count": 0,
                "category_chooser_token": None,
                "question": None,
                "deadline": 0,
                "team_round": False,
                "teams": {},
                "answers": {},
                "team_answers": {},
                "scores": {token: 0 for token in self.state["players"]},
                "processed_requests": {},
            }
        )
        self.mark_changed()
        await self.emit_event(
            "GAME_RESET",
            scores={
                self.state["players"][token]["player_id"]: score
                for token, score in self.state["scores"].items()
            },
            message="Neues Spiel startet.",
        )

    async def start_category_selection(self):
        """Fordere den naechsten Spieler zur Kategorieauswahl auf."""
        categories = self.available_categories()
        if not categories:
            self.state["phase"] = "game_over"
            self.mark_changed()
            await self.emit_event(
                "GAME_OVER",
                scores=self.public_scores(),
                message="Spiel beendet.",
            )
            return

        chooser_token = self.category_chooser()
        if not chooser_token:
            await asyncio.sleep(0.5)
            return

        self.state["phase"] = "category_select"
        self.state["category_chooser_token"] = chooser_token
        self.state["current_category"] = None
        self.state["category_round_count"] = 0
        self.state["question"] = None
        self.state["deadline"] = 0
        self.state["team_round"] = False
        self.state["teams"] = {}
        self.state["answers"] = {}
        self.state["team_answers"] = {}
        self.mark_changed()
        chooser = self.state["players"][chooser_token]
        await self.emit_event(
            "CATEGORY_SELECTION",
            categories=categories,
            chooser_id=chooser["player_id"],
            chooser_name=chooser["name"],
            block_size=CATEGORY_BLOCK_SIZE,
        )

    def next_question_index(self):
        """Nimm die naechste Frage aus dem aktuell gewaehlten Kategorie-Pool."""
        category = self.state.get("current_category")
        if not category:
            return None
        pool = self.state["category_questions"].get(category, [])
        if not pool:
            return None
        return pool.pop(0)

    async def start_next_round(self):
        """Beende gegebenenfalls das Spiel oder veroeffentliche die naechste Frage."""
        if (
            not self.state.get("current_category")
            or self.state.get("category_round_count", 0) >= CATEGORY_BLOCK_SIZE
        ):
            await self.start_category_selection()
            return

        round_number = self.state["round"] + 1
        question_index = self.next_question_index()
        if question_index is None:
            await self.start_category_selection()
            return

        question = self.questions[question_index]
        # Jede dritte Runde ist eine Teamrunde.
        team_round = round_number % 3 == 0
        self.state.update(
            {
                "phase": "question",
                "round": round_number,
                "category_round_count": self.state.get("category_round_count", 0) + 1,
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
        # Die getrennten Ereignisse machen die Phasen fuer Clients eindeutig
        # nachvollziehbar und erhalten jeweils eine Sequenznummer.
        await self.emit_event(
            "QUESTION",
            round=round_number,
            question=question["frage"],
            category=question.get("kategorie", self.state["current_category"]),
            category_round=self.state["category_round_count"],
            category_block_size=CATEGORY_BLOCK_SIZE,
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
        """Mische verbundene Spieler und bilde Zweiergruppen."""
        players = list(self.connected_tokens())
        random.shuffle(players)
        return {
            f"Team {index // 2 + 1}": players[index : index + 2]
            for index in range(0, len(players) - 1, 2)
        }

    def public_teams(self):
        """Wandle interne Tokens in fuer Clients geeignete Teamdaten um."""
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
        """Erzeuge eine Ranglistenansicht ohne geheime Sitzungstokens."""
        return {
            self.state["players"][token]["name"]: score
            for token, score in self.state["scores"].items()
        }

    async def evaluate_round(self):
        """Vergleiche Antworten, vergebe Punkte und veroeffentliche das Ergebnis."""
        correct = self.state["question"]["antwort"].strip().casefold()
        results = {}

        if self.state["team_round"]:
            # Teammitglieder teilen Antwort und Bewertung. Nicht zugeordnete
            # Spieler, etwa bei ungerader Anzahl, werden einzeln ausgewertet.
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
