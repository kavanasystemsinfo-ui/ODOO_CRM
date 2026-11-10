"""Copias por visitante: la parte pura (sin Odoo ni base de datos).

Quien quiere probar la demo con libertad recibe una copia privada de la base,
que caduca. Aquí viven las reglas que no necesitan Odoo, para poder probarlas
sin servidor:

  * el nombre de cada copia (solo los que generamos: el SQL los usa);
  * la cookie que dice qué copia es tuya, firmada con HMAC-SHA256 para que
    nadie pueda ponerse el nombre de la copia de otro;
  * qué copias hay que borrar y cuándo reiniciar el Odoo de pruebas.

Lo usan controllers/pruebas.py (dentro de Odoo) y panel/limpiar_pruebas.py
(en el servidor, como root).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

PREFIJO = 'muebles_demo_'
PLANTILLA = 'muebles_plantilla'
COOKIE = 'muebles_prueba'
NOMBRE_RE = re.compile(r'^muebles_demo_[a-z0-9]{4,12}$')
DURACION = 60 * 60           # una hora de prueba
TOPE = 3                     # copias a la vez: lo que cabe en el VPS de 4 GB
GRACIA = 5 * 60              # la base se borra 5 min después de caducar la cookie
REINICIAR_CON_VIEJAS = 3     # registros de bases borradas que se toleran en memoria


def nombre_valido(nombre: str | None) -> bool:
    return bool(nombre) and bool(NOMBRE_RE.fullmatch(nombre))


def nuevo_nombre() -> str:
    alfabeto = 'abcdefghijklmnopqrstuvwxyz0123456789'
    return PREFIJO + ''.join(secrets.choice(alfabeto) for _ in range(8))


def _firma(cuerpo: str, secreto: str) -> str:
    return hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).hexdigest()


def firmar(nombre: str, caduca: int, secreto: str) -> str:
    """Valor de la cookie: «nombre.caduca.firma»."""
    if not secreto:
        raise ValueError('sin secreto no se firma nada')
    if not nombre_valido(nombre):
        raise ValueError(f'nombre de copia no válido: {nombre!r}')
    cuerpo = f'{nombre}.{int(caduca)}'
    return f'{cuerpo}.{_firma(cuerpo, secreto)}'


def verificar(valor: str | None, secreto: str, ahora: float | None = None) -> tuple[str, int] | None:
    """(nombre, caduca) si la cookie es auténtica y no ha caducado; si no, None."""
    if not valor or not secreto:
        return None
    partes = valor.split('.')
    if len(partes) != 3:
        return None
    nombre, caduca, firma = partes
    if not nombre_valido(nombre) or not caduca.isdigit():
        return None
    if not hmac.compare_digest(firma, _firma(f'{nombre}.{caduca}', secreto)):
        return None
    if int(caduca) <= (time.time() if ahora is None else ahora):
        return None
    return nombre, int(caduca)


def comentario(caduca: int) -> str:
    """Lo que se guarda en la propia base (COMMENT ON DATABASE)."""
    return f'caduca={int(caduca)}'


def leer_caducidad(texto: str | None) -> int:
    """0 si la base no dice cuándo caduca: se trata como caducada."""
    m = re.fullmatch(r'caduca=(\d+)', (texto or '').strip())
    return int(m.group(1)) if m else 0


def plazas_ocupadas(copias: dict[str, int], ahora: float) -> int:
    """Copias que cuentan contra el tope: todas las que aún existen."""
    return len(copias)


def libre_en_minutos(copias: dict[str, int], ahora: float) -> int:
    """Cuándo queda libre la primera plaza (caducidad + gracia)."""
    if not copias:
        return 0
    primera = min(copias.values()) + GRACIA
    return max(1, int((primera - ahora) // 60) + 1)


def a_borrar(copias: dict[str, int], ahora: float) -> list[str]:
    """Copias cuya cookie ya caducó hace más de la gracia."""
    return sorted(n for n, caduca in copias.items()
                  if nombre_valido(n) and caduca + GRACIA <= ahora)


def reiniciar_odoo(borradas_ahora: int, quedan_vivas: int, viejas_antes: int) -> tuple[bool, int]:
    """¿Reiniciar el Odoo de pruebas para soltar de memoria las bases borradas?

    Odoo guarda en memoria el registro de cada base que ha servido y no lo
    suelta al borrarla. Se reinicia cuando no queda nadie probando (no molesta)
    o cuando ya hay demasiados registros muertos (memoria). Devuelve
    (reiniciar, registros muertos que quedan en memoria).
    """
    viejas = viejas_antes + borradas_ahora
    if viejas and (quedan_vivas == 0 or viejas >= REINICIAR_CON_VIEJAS):
        return True, 0
    return False, viejas
