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

connected_clients = set()

game_started = False
current_question = None
answers = {}


def get_random_question():
    """
    Holt eine zufällige Frage aus der TinyDB.
    """

    questions = db.all()

    if not questions:
        return None

    return random.choice(questions)


async def broadcast(message):
    """
    Sendet eine Nachricht an alle aktuell verbundenen Clients.
    """

    if not connected_clients:
        return

    disconnected_clients = set()
    message_json = json.dumps(message)

    for client in connected_clients.copy():
        try:
            await client.send(message_json)
        except websockets.ConnectionClosed:
            disconnected_clients.add(client)

    for client in disconnected_clients:
        connected_clients.remove(client)


async def start_game_if_ready():
    """
    Startet das Spiel, sobald genug Clients verbunden sind.
    """

    global game_started
    global current_question

    if game_started:
        return

    if len(connected_clients) < MIN_PLAYERS:
        print(f"(server) Warte auf Spieler: {len(connected_clients)}/{MIN_PLAYERS}")
        return

    game_started = True
    current_question = get_random_question()

    if current_question is None:
        await broadcast({
            "type": "error",
            "message": "Keine Fragen in der Datenbank gefunden."
        })
        return

    print("(server) Spiel startet")
    print(f"(server) Frage: {current_question['frage']}")

    await broadcast({
        "type": "question",
        "data": {
            "frage": current_question["frage"]
        }
    })


async def handle_client(websocket):
    """
    Wird automatisch aufgerufen,
    sobald sich ein Client verbindet.
    """

    connected_clients.add(websocket)

    client_addr = websocket.remote_address
    print(f"(server) Client verbunden: {client_addr}")

    await websocket.send(json.dumps({
        "type": "info",
        "message": f"Verbunden. Warte auf Spieler: {len(connected_clients)}/{MIN_PLAYERS}"
    }))

    await start_game_if_ready()

    try:
        async for message in websocket:
            print(f"(server) Antwort erhalten von {client_addr}: {message}")

            if not game_started:
                await websocket.send(json.dumps({
                    "type": "info",
                    "message": f"Spiel startet erst bei {MIN_PLAYERS} Spielern."
                }))
                continue

            if current_question is None:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Keine aktuelle Frage vorhanden."
                }))
                continue

            user_answer = message.strip()
            correct_answer = current_question["antwort"].strip()

            is_correct = user_answer.lower() == correct_answer.lower()

            answers[str(client_addr)] = {
                "answer": user_answer,
                "correct": is_correct
            }

            if is_correct:
                response_text = "Richtig!"
            else:
                response_text = f"Falsch! Richtige Antwort: {correct_answer}"

            await websocket.send(json.dumps({
                "type": "response",
                "message": response_text
            }))

    except websockets.ConnectionClosed:
        print(f"(server) Verbindung getrennt: {client_addr}")

    finally:
        connected_clients.remove(websocket)
        print(f"(server) Aktive Clients: {len(connected_clients)}")


async def start_server():
    """
    Startet den WebSocket-Server.
    """

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