"""Plan de cada tramo de la jornada simulada (lógica pura, sin Odoo).

La empresa ficticia trabaja en tramos: tres al día de lunes a viernes y uno el
sábado. Cada tramo tiene una clave («2026-11-10#13») y todo lo que pasa en él
sale de un generador aleatorio sembrado con esa clave: el mismo tramo produce
siempre el mismo plan, así que un fallo se puede reproducir y una segunda
ejecución no inventa otra historia.

Aquí solo se decide CUÁNTO pasa y con qué textos; QUÉ registros se tocan lo
decide el simulador dentro de Odoo (models/simulador_empresa.py), siguiendo el
estado real de la base.
"""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from datetime import datetime

# Hora local (Europe/Madrid) en que arranca cada tramo, por día de la semana.
TRAMOS = {0: (9, 13, 17), 1: (9, 13, 17), 2: (9, 13, 17), 3: (9, 13, 17),
          4: (9, 13, 17), 5: (11,), 6: ()}

# Dominio reservado (RFC 2606): ningún correo simulado puede llegar a nadie real.
SUFIJO_FICTICIO = ".example"

_NOMBRES = ("Laura", "Pau", "Marta", "Jordi", "Núria", "Sergio", "Elena", "Vicent",
            "Carmen", "Andreu", "Lucía", "Óscar", "Irene", "Xavier", "Rosa", "Hugo")
_APELLIDOS = ("Ferrer", "Martí", "Soler", "Navarro", "Gil", "Ribes", "Llorens",
              "Moreno", "Castell", "Vidal", "Sanchis", "Peris", "Roig", "Bosch")
_TIPOS = ("Hotel", "Interiorismo", "Estudio", "Reformas", "Apartamentos",
          "Coworking", "Restaurante", "Clínica", "Constructora", "Residencia")
_LUGARES = ("Benicàssim", "Vila-real", "Morella", "Peníscola", "Onda", "Burriana",
            "Alzira", "Gandia", "Xàtiva", "Dénia", "Sagunt", "Vinaròs")
_ASUNTOS = (
    "Amueblar {n} habitaciones", "Sillas para la terraza ({n} uds)",
    "Mesas para la sala de reuniones", "Renovación del comedor ({n} plazas)",
    "Mobiliario para {n} apartamentos turísticos", "Sofás para la recepción",
    "Camas y mesitas para {n} habitaciones", "Muestra de tapizados para obra nueva",
)
_CORREOS_CLIENTE = (
    "Buenos días, ¿podéis confirmar plazo de entrega para el pedido?",
    "Nos encaja la propuesta. ¿Se puede ajustar el acabado de la madera?",
    "Adjunto planos de la obra; necesitamos medidas antes del viernes.",
    "¿Tenéis muestra del tejido en gris? La pasaríamos a recoger.",
    "Hemos revisado el presupuesto con dirección; os decimos algo esta semana.",
    "¿Podríais incluir el montaje en el precio?",
)
_FEEDBACK = (
    "Llamada hecha: interesado, pide presupuesto por escrito.",
    "Hablado con compras: quieren ver la muestra en tienda.",
    "Confirma medidas y plazo; seguimos la semana que viene.",
    "No contesta; se deja mensaje y se vuelve a intentar.",
    "Reunión breve: comparan con otro proveedor, el precio pesa.",
)


def clave_tramo(momento: datetime) -> str | None:
    """Clave del último tramo que ya ha empezado ese día, o None si aún no hay."""
    horas = [h for h in TRAMOS[momento.weekday()] if h <= momento.hour]
    if not horas:
        return None
    return f"{momento.date().isoformat()}#{horas[-1]:02d}"


def generador(clave: str) -> random.Random:
    """Aleatorio reproducible: misma clave, misma secuencia."""
    semilla = int.from_bytes(hashlib.sha256(clave.encode()).digest()[:8], "big")
    return random.Random(semilla)  # noqa: S311 - simulación, no criptografía


def plan_tramo(clave: str) -> dict[str, int]:
    """Cuántas cosas pasan en el tramo. Volúmenes de una pyme de muebles."""
    rng = generador(clave + "/plan")
    return {
        "leads_nuevos": rng.choice((0, 1, 1, 2)),
        "cualificaciones": rng.choice((0, 1, 1)),
        "propuestas": rng.choice((0, 1)),
        "correos_cliente": rng.randint(1, 3),
        "actividades_hechas": rng.randint(1, 2),
        "actividades_nuevas": rng.randint(1, 2),
        "pedidos_recurrentes": rng.choice((0, 0, 1)),
        "confirmaciones": rng.choice((0, 1, 1)),
        "perdidas": 1 if rng.random() < 0.15 else 0,
        "entregas": rng.randint(0, 2),
        "facturas": 3,
        "cobros": rng.randint(0, 2),
        "recepciones": rng.choice((0, 1)),
        "facturas_proveedor": rng.choice((0, 1)),
    }


def sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def dominio_ficticio(nombre: str) -> str:
    """«Hotel Morella S.L.» -> «hotelmorella.example»."""
    limpio = re.sub(r"\b(s\.?l\.?u?|s\.?a\.?)\W*$", "", sin_acentos(nombre).lower())
    base = re.sub(r"[^a-z0-9]", "", limpio)[:30] or "cliente"
    return base + SUFIJO_FICTICIO


def es_email_ficticio(email: str | None) -> bool:
    """Solo valen dominios reservados: *.example o example.com/.org/.net."""
    if not email or "@" not in email:
        return True  # sin correo no hay a quién escribir
    dominio = email.rsplit("@", 1)[1].strip().lower().rstrip(">")
    return dominio.endswith(SUFIJO_FICTICIO) or dominio in (
        "example.com", "example.org", "example.net")


def email_ficticio(persona: str, dominio: str) -> str:
    usuario = re.sub(r"[^a-z.]", "", sin_acentos(persona).lower().replace(" ", "."))
    return f"{usuario or 'contacto'}@{dominio}"


def persona(rng: random.Random) -> str:
    return f"{rng.choice(_NOMBRES)} {rng.choice(_APELLIDOS)}"


def empresa(rng: random.Random) -> str:
    return f"{rng.choice(_TIPOS)} {rng.choice(_LUGARES)}"


def asunto(rng: random.Random) -> str:
    return rng.choice(_ASUNTOS).format(n=rng.choice((4, 6, 8, 12, 20, 30)))


def correo_cliente(rng: random.Random) -> str:
    return rng.choice(_CORREOS_CLIENTE)


def feedback_llamada(rng: random.Random) -> str:
    return rng.choice(_FEEDBACK)
