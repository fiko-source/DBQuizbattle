from dotenv import load_dotenv
import os

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))
SERVER_ID = int(os.getenv("SERVER_ID"))