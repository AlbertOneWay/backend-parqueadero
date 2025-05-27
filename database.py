import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["parqueadero"]

coleccion_eventos = db["eventos"]
coleccion_usuarios = db["usuarios"]
