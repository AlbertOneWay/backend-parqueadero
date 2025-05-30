from pydantic import BaseModel
from typing import List
from datetime import datetime

class Vehiculo(BaseModel):
    placa: str
    tipo_vehiculo: str

class Usuario(BaseModel):
    nombre: str
    telefono: str
    password: str
    rol: str = "usuario"  # Valor por defecto si no se especifica

class VehiculoRegistro(BaseModel):
    telefono: str  # Para identificar al usuario dueño
    vehiculo: Vehiculo

class Evento(BaseModel):
    evento: str
    tipo_vehiculo: str
    placa: str
    hora: datetime
