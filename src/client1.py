import asyncio
import websockets
from dotenv import load_dotenv
import os

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

SERVER_URI = f"ws://{SERVER_IP}:{SERVER_PORT}"


async def start_client():
    """
    Verbindet sich mit dem WebSocket-Server
    und sendet Nachrichten.
    """

    async with websockets.connect(SERVER_URI) as websocket:
        print(f"(client) Verbunden mit {SERVER_URI}")

        while True:
            message = input("(client) Nachricht eingeben: ")

            await websocket.send(message)
            print(f"(client) Gesendet: {message}")

            response = await websocket.recv()
            print(f"(client) Antwort vom Server: {response}")


if __name__ == "__main__":
    asyncio.run(start_client())