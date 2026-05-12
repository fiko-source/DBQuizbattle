import asyncio
import websockets
from dotenv import load_dotenv
import os

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))


connected_clients = set()


async def handle_client(websocket):
    """
    Wird automatisch aufgerufen,
    sobald sich ein Client verbindet.
    """

    # Client speichern
    connected_clients.add(websocket)

    client_addr = websocket.remote_address
    print(f"(server) Client verbunden: {client_addr}")

    try:
        # Nachrichten dauerhaft empfangen
        async for message in websocket:

            print(f"(server) Nachricht erhalten: {message}")

            response = f"Server hat empfangen: {message}"

            # Antwort an denselben Client
            await websocket.send(response)

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
        await asyncio.Future()  # läuft für immer


if __name__ == "__main__":
    asyncio.run(start_server())