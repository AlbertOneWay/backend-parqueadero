from fastapi import FastAPI, HTTPException, Body
from models import Evento, Usuario, VehiculoRegistro
from database import coleccion_eventos, coleccion_usuarios
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from pymongo import DESCENDING
from sms import enviar_sms
import bcrypt
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringe esto a tu dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def normalizar_placa(placa: str) -> str:
    return re.sub(r'\W+', '', placa).upper()

# -------------------------------
# Registrar nuevo usuario (sin vehículos)
# -------------------------------
@app.post("/usuario")
def registrar_usuario(usuario: Usuario):
    if coleccion_usuarios.find_one({"telefono": usuario.telefono}):
        raise HTTPException(status_code=400, detail="Este usuario ya existe.")

    hashed_password = bcrypt.hashpw(usuario.password.encode("utf-8"), bcrypt.gensalt())

    coleccion_usuarios.insert_one({
        "nombre": usuario.nombre,
        "telefono": usuario.telefono,
        "password": hashed_password.decode("utf-8"),
        "vehiculos": [],
        "rol": "usuario"  # Puedes cambiarlo a "admin" si corresponde
    })

    return {"status": "usuario registrado"}

@app.post("/evento/manual")
def registrar_evento_manual(
    evento: Evento,
    telefono_admin: str = Body(...),
    password_admin: str = Body(...)
):
    admin = coleccion_usuarios.find_one({"telefono": telefono_admin})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin no encontrado")

    if not bcrypt.checkpw(password_admin.encode("utf-8"), admin["password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    if admin.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="No autorizado. No es administrador.")

    evento.placa = normalizar_placa(evento.placa)
    coleccion_eventos.insert_one(evento.dict())

    mensaje = f"ADMIN registró {evento.evento.upper()} para {evento.placa} a las {evento.hora.strftime('%Y-%m-%d %H:%M:%S')}"
    print(f"[ADMIN] {mensaje}")

    return {"status": "Evento manual registrado correctamente", "mensaje": mensaje}

@app.post("/login")
def login(nombre: str = Body(...), password: str = Body(...)):
    usuario = coleccion_usuarios.find_one({"nombre": nombre})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not bcrypt.checkpw(password.encode("utf-8"), usuario["password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    return {
    "nombre": usuario["nombre"],
    "telefono": usuario["telefono"],
    "rol": usuario.get("rol", "usuario")
    }

# -------------------------------
# Agregar un vehículo a un usuario ya registrado
# -------------------------------
@app.post("/vehiculo")
def agregar_vehiculo(data: VehiculoRegistro):
    data.vehiculo.placa = normalizar_placa(data.vehiculo.placa)

    resultado = coleccion_usuarios.update_one(
        {"telefono": data.telefono},
        {"$addToSet": {"vehiculos": data.vehiculo.dict()}}
    )
    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"status": "vehículo agregado al usuario"}

@app.get("/vehiculos/{telefono}")
def obtener_vehiculos(telefono: str):
    usuario = coleccion_usuarios.find_one({"telefono": telefono})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario["vehiculos"]

@app.get("/usuario/{telefono}/vehiculos-activos")
def vehiculos_activos(telefono: str):
    usuario = coleccion_usuarios.find_one({"telefono": telefono})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    vehiculos = usuario.get("vehiculos", [])
    activos = []

    for v in vehiculos:
        placa = normalizar_placa(v["placa"])
        ultimo_evento = coleccion_eventos.find({"placa": placa}).sort("hora", -1).limit(1)
        evento = next(ultimo_evento, None)
        if evento and evento["evento"] == "entrada":
            activos.append({
                "placa": placa,
                "tipo": evento["tipo_vehiculo"],
                "hora_entrada": evento["hora"]
            })

    return activos

# -------------------------------
# Registrar un evento y verificar si debe enviar SMS
# -------------------------------
@app.post("/evento")
def registrar_evento(data: Evento):
    data.placa = normalizar_placa(data.placa)
    coleccion_eventos.insert_one(data.dict())

    usuario = coleccion_usuarios.find_one({
        "vehiculos.placa": data.placa
    })

    if usuario:
        nombre = usuario["nombre"]
        telefono = usuario["telefono"]
        mensaje = f"Hola {nombre}, tu vehículo {data.placa} hizo {data.evento} el {data.hora.strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            sid = enviar_sms(telefono, mensaje)
            print(f"[SMS] Enviado a {telefono} | SID: {sid}")
        except Exception as e:
            print(f"[ERROR] No se pudo enviar SMS: {e}")

    return {"status": "evento registrado"}

# -------------------------------
# Consultar eventos por placa
# -------------------------------
@app.get("/vehiculo/{placa}")
def obtener_historial(placa: str):
    placa = normalizar_placa(placa)
    eventos = list(coleccion_eventos.find({"placa": placa}).sort("hora", DESCENDING))
    for e in eventos:
        e["_id"] = str(e["_id"])
    return eventos

# -------------------------------
# Consultar disponibilidad de parqueo
# -------------------------------
@app.get("/disponibilidad")
def disponibilidad():
    return calcular_disponibilidad()

def calcular_disponibilidad():
    placas_carros_raw = coleccion_eventos.distinct("placa", {"tipo_vehiculo": "carro"})
    placas_motos_raw = coleccion_eventos.distinct("placa", {"tipo_vehiculo": "moto"})

    placas_carros = set([normalizar_placa(p) for p in placas_carros_raw])
    placas_motos = set([normalizar_placa(p) for p in placas_motos_raw])

    carros_dentro = 0
    motos_dentro = 0

    for placa in placas_carros:
        ultimo = coleccion_eventos.find_one(
            {"placa": placa, "tipo_vehiculo": "carro"},
            sort=[("hora", DESCENDING)]
        )
        if ultimo and ultimo["evento"] == "entrada":
            carros_dentro += 1

    for placa in placas_motos:
        ultimo = coleccion_eventos.find_one(
            {"placa": placa, "tipo_vehiculo": "moto"},
            sort=[("hora", DESCENDING)]
        )
        if ultimo and ultimo["evento"] == "entrada":
            motos_dentro += 1

    return {
        "puestos_carro_disponibles": max(24 - carros_dentro, 0),
        "puestos_moto_disponibles": max(50 - motos_dentro, 0)
    }

@app.get("/usuario/{telefono}/historial-eventos")
def historial_eventos_usuario(telefono: str):
    usuario = coleccion_usuarios.find_one({"telefono": telefono})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    vehiculos = usuario.get("vehiculos", [])
    if not vehiculos:
        return {"historial": []}

    placas_usuario = [normalizar_placa(v["placa"]) for v in vehiculos]

    eventos = list(coleccion_eventos.find(
        {"placa": {"$in": placas_usuario}}
    ).sort("hora", DESCENDING))

    for e in eventos:
        e["_id"] = str(e["_id"])  # Para evitar problemas con ObjectId
    return {"historial": eventos}

@app.get("/usuario/{telefono}/vehiculo/{placa}/historial")
def historial_eventos_por_placa(telefono: str, placa: str):
    usuario = coleccion_usuarios.find_one({"telefono": telefono})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    placa_normalizada = normalizar_placa(placa)
    placas_usuario = [normalizar_placa(v["placa"]) for v in usuario.get("vehiculos", [])]

    if placa_normalizada not in placas_usuario:
        raise HTTPException(status_code=403, detail="La placa no está registrada para este usuario")

    eventos = list(coleccion_eventos.find(
        {"placa": placa_normalizada}
    ).sort("hora", DESCENDING))

    for e in eventos:
        e["_id"] = str(e["_id"])

    return {"placa": placa_normalizada, "eventos": eventos}


# -------------------------------
# Obtener pico y placa del día
# -------------------------------
@app.get("/pico-y-placa")
def pico_y_placa():
    dia = datetime.now().weekday()  # 0 = lunes
    pico = {
        0: ["1", "2"],
        1: ["3", "4"],
        2: ["5", "6"],
        3: ["7", "8"],
        4: ["9", "0"],
        5: [],
        6: []
    }
    return {"dia": dia, "placas_restringidas": pico[dia]}

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
