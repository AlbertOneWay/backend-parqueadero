import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

twilio_sid = os.getenv("TWILIO_SID")
twilio_token = os.getenv("TWILIO_TOKEN")
twilio_from = os.getenv("TWILIO_FROM")

client = Client(twilio_sid, twilio_token)

def enviar_sms(destino: str, mensaje: str):
    message = client.messages.create(
        body=mensaje,
        from_=twilio_from,
        to=destino
    )
    return message.sid
