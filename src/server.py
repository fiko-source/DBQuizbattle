import asyncio
import websockets
from dotenv import load_dotenv
import os
from tinydb import TinyDB
import json
import random

load_dotenv()

db = TinyDB("../tinydb.json")

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

MIN_PLAYERS = 3
ROUND_TIME = 20

connected_clients = set()

game_started = False
current_question = None
current_round = 0
answers = {}
scores = {}

next_player_id = 1
client_ids = {}


def get_all_questions():
    questions = db.all()
    random.shuffle(questions)
    return questions


async def broadcast(message):
    if not connected_clients:
        return

    message_json = json.dumps(message)

    disconnected_clients = set()

    for client in connected_clients.copy():
        try:
            await client.send(message_json)
        except websockets.ConnectionClosed:
            disconnected_clients.add(client)

    for client in disconnected_clients:
        connected_clients.remove(client)


async def start_game_if_ready():
    global game_started

    if game_started:
        return

    if len(connected_clients) < MIN_PLAYERS:
        print(f"(server) Warte auf Spieler: {len(connected_clients)}/{MIN_PLAYERS}")
        return

    game_started = True

    print("(server) Genug Spieler verbunden. Spiel startet.")

    asyncio.create_task(game_loop())


async def game_loop():
    global current_question
    global current_round
    global answers

    questions = get_all_questions()

    if not questions:
        await broadcast({
            "type": "error",
            "message": "Keine Fragen in der Datenbank gefunden."
        })
        return

    for question in questions:
        current_round += 1
        current_question = question
        answers = {}

        print(f"(server) Runde {current_round} startet")
        print(f"(server) Frage: {current_question['frage']}")

        await broadcast({
            "type": "question",
            "round": current_round,
            "time": ROUND_TIME,
            "data": {
                "frage": current_question["frage"]
            }
        })

        await asyncio.sleep(ROUND_TIME)

        await evaluate_round()

        await asyncio.sleep(3)

    await broadcast({
        "type": "game_over",
        "message": "Spiel beendet.",
        "scores": scores
    })

    print("(server) Spiel beendet.")


async def evaluate_round():
    correct_answer = current_question["antwort"].strip().lower()

    results = {}

    for client in connected_clients:
        client_id = client_ids[client]

        user_answer = answers.get(client_id)

        if user_answer is None:
            results[client_id] = {
                "answer": None,
                "correct": False
            }
            scores[client_id] = scores.get(client_id, 0)
            continue

        is_correct = user_answer.strip().lower() == correct_answer

        if is_correct:
            scores[client_id] = scores.get(client_id, 0) + 1
        else:
            scores[client_id] = scores.get(client_id, 0)

        results[client_id] = {
            "answer": user_answer,
            "correct": is_correct
        }

    await broadcast({
        "type": "result",
        "correct_answer": current_question["antwort"],
        "results": results,
        "scores": scores
    })


async def handle_client(websocket):
    global next_player_id

    connected_clients.add(websocket)

    player_id = f"Player {next_player_id}"
    next_player_id += 1

    client_ids[websocket] = player_id
    scores[player_id] = 0

    client_addr = websocket.remote_address
    print(f"(server) {player_id} verbunden: {client_addr}")

    await websocket.send(json.dumps({
        "type": "welcome",
        "player_id": player_id,
        "message": f"Verbunden als {player_id}"
    }))

    await websocket.send(json.dumps({
        "type": "info",
        "message": f"Verbunden. Warte auf Spieler: {len(connected_clients)}/{MIN_PLAYERS}"
    }))

    await start_game_if_ready()

    try:
        async for message in websocket:
            print(f"(server) Antwort erhalten von {player_id}: {message}")

            if not game_started or current_question is None:
                await websocket.send(json.dumps({
                    "type": "info",
                    "message": "Aktuell läuft keine Frage."
                }))
                continue

            if player_id in answers:
                await websocket.send(json.dumps({
                    "type": "info",
                    "message": "Du hast für diese Runde bereits geantwortet."
                }))
                continue

            answers[player_id] = message

            await websocket.send(json.dumps({
                "type": "info",
                "message": "Antwort gespeichert."
            }))

    except websockets.ConnectionClosed:
        print(f"(server) Verbindung getrennt: {player_id}")

    finally:
        connected_clients.remove(websocket)
        client_ids.pop(websocket, None)
        print(f"(server) Aktive Clients: {len(connected_clients)}")


async def start_server():
    print(f"(server) läuft auf ws://{SERVER_IP}:{SERVER_PORT}")
    print(f"(server) Warte auf mindestens {MIN_PLAYERS} Spieler...")

    async with websockets.serve(
        handle_client,
        SERVER_IP,
        SERVER_PORT
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(start_server())