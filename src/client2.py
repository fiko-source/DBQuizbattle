import asyncio
import websockets
from dotenv import load_dotenv
import os
import json

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

SERVER_URI = f"ws://{SERVER_IP}:{SERVER_PORT}"


async def start_client():
    async with websockets.connect(SERVER_URI) as websocket:
        print(f"(client) Verbunden mit {SERVER_URI}")

        while True:
            server_message = await websocket.recv()
            data = json.loads(server_message)

            if data["type"] == "info":
                print(f"(server) {data['message']}")

            elif data["type"] == "question":
                question = data["data"]

                print("\n=== Neue Frage ===")
                print(question["frage"])

                answer = input("\n(client) Antwort eingeben: ")
                await websocket.send(answer)

            elif data["type"] == "response":
                print(f"(server) {data['message']}")

            elif data["type"] == "error":
                print(f"(error) {data['message']}")


if __name__ == "__main__":
    asyncio.run(start_client())