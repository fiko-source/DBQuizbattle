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

connected_clients = set()


def get_random_question():
    """
    Holt eine zufällige Frage aus der TinyDB.
    """

    questions = db.all()

    if not questions:
        return None

    return random.choice(questions)


async def handle_client(websocket):
    """
    Wird automatisch aufgerufen,
    sobald sich ein Client verbindet.
    """

    connected_clients.add(websocket)

    client_addr = websocket.remote_address
    print(f"(server) Client verbunden: {client_addr}")

    try:
        question = get_random_question()

        if question is None:
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Keine Fragen in der Datenbank gefunden."
            }))
        else:
            await websocket.send(json.dumps({
                "type": "question",
                "data": question
            }))

        async for message in websocket:
            print(f"(server) Nachricht erhalten: {message}")

            response = {
                "type": "response",
                "message": f"Server hat empfangen: {message}"
            }

            await websocket.send(json.dumps(response))

    except websockets.ConnectionClosed:
        print(f"(server) Verbindung getrennt: {client_addr}")

    finally:
        connected_clients.remove(websocket)


async def start_server():
    """
    Startet den WebSocket-Server.
    """

    print(f"(server) läuft auf ws://{SERVER_IP}:{SERVER_PORT}")

    async with websockets.serve(
        handle_client,
        SERVER_IP,
        SERVER_PORT
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(start_server())