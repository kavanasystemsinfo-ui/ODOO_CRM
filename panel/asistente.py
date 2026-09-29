#!/usr/bin/env python3
"""Asistente técnico del laboratorio de muebles.

Para qué: quien visita la demo (o un reclutador) puede preguntar cómo está
hecho el proyecto sin leerse el repositorio. Responde **solo** con lo que hay
en los documentos reales del repositorio: README, decisiones, tests, panel,
scripts, modelos, vistas y permisos.

Cómo:
  1. Trocea esos documentos en fragmentos.
  2. Busca los fragmentos que mejor responden (puntuación léxica, sin
     dependencias: librería estándar).
  3. Si hay clave de modelo, redacta la respuesta con esos fragmentos como
     único contexto y la cita. Si no hay clave, devuelve los fragmentos tal
     cual y lo declara: no se aparenta nada.

Uso:
    from asistente import responder
    responder("¿cómo se comprueba que el almacén cuadra?")
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent

FICHEROS_SUELTOS = ("README.md", "DECISIONS.md", "SECURITY.md", "pytest.ini", "requirements-dev.txt")
CARPETAS = ("tests", "panel", "scripts", "models", "controllers", "views", "security", "data")
EXTENSIONES = (".md", ".py", ".xml", ".csv", ".ini", ".txt", ".json")
IGNORAR = ("__pycache__", "cache_panel", "landing", "video", "districthome_products.json")

LINEAS_POR_FRAGMENTO = 28
MAX_FRAGMENTOS = 5

# Caché por proceso: leer el repositorio y contar términos en cada pregunta
# sería tirar el trabajo hecho. El panel es un servicio de larga vida.
_CACHE: dict[str, Any] = {"documentos": None, "frecuencias": None}

URL_MODELO = "https://openrouter.ai/api/v1/chat/completions"
MODELO_POR_DEFECTO = os.environ.get("MUEBLES_LLM_MODEL", "openai/gpt-4o-mini")
FICHEROS_CLAVE = (
    "/root/.hermes/profiles/hermes2/.env",
    "/root/.hermes/profiles/kavana/.env",
)

INSTRUCCIONES = (
    "Eres el asistente técnico del proyecto ODOO_CRM (laboratorio de empresa "
    "ficticia de muebles sobre Odoo 17). Respondes en español, en 2 a 5 frases, "
    "solo con lo que digan los fragmentos del repositorio que se te dan. Si la "
    "respuesta no está en los fragmentos, dilo claramente en vez de inventarla. "
    "Cita el fichero cuando uses algo concreto. No hables de temas ajenos al "
    "proyecto."
)

VACIAS = {
    "de", "la", "el", "los", "las", "un", "una", "y", "o", "que", "en", "con",
    "por", "para", "del", "al", "se", "es", "son", "como", "cual", "donde",
    "the", "a", "of", "to", "how", "what", "is", "are", "and", "or", "it",
}


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _terminos(texto: str) -> list[str]:
    palabras = re.findall(r"[a-z0-9_]{3,}", _sin_acentos(texto.lower()))
    return [p for p in palabras if p not in VACIAS]


def _fragmentos() -> list[tuple[str, int, str]]:
    """Trocea los documentos del repositorio en (fichero, línea inicial, texto)."""
    encontrados: list[tuple[str, int, str]] = []
    candidatos: list[Path] = []
    for nombre in FICHEROS_SUELTOS:
        ruta = RAIZ / nombre
        if ruta.is_file():
            candidatos.append(ruta)
    for carpeta in CARPETAS:
        base = RAIZ / carpeta
        if not base.is_dir():
            continue
        for ruta in sorted(base.rglob("*")):
            if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
                continue
            if any(parte in IGNORAR for parte in ruta.parts) or ruta.name in IGNORAR:
                continue
            candidatos.append(ruta)

    for ruta in candidatos:
        try:
            lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        relativo = str(ruta.relative_to(RAIZ))
        if ruta.suffix.lower() == ".md":
            encontrados.extend(_trocear_markdown(relativo, lineas))
            continue
        for inicio in range(0, len(lineas), LINEAS_POR_FRAGMENTO):
            trozo = "\n".join(lineas[inicio:inicio + LINEAS_POR_FRAGMENTO]).strip()
            if len(trozo) >= 40:
                encontrados.append((relativo, inicio + 1, trozo))
    return encontrados


def _trocear_markdown(relativo: str, lineas: list[str]) -> list[tuple[str, int, str]]:
    """Un fragmento por bloque del markdown, con su título por delante.

    Así «Almacén cuadrado» viaja junto al texto que lo explica y una pregunta
    sobre el almacén lo encuentra, aunque el fichero tenga cientos de líneas.
    """
    bloques: list[tuple[str, int, str]] = []
    titulo = ""
    inicio = 1
    buffer: list[str] = []

    def cerrar() -> None:
        if len("\n".join(buffer).strip()) >= 40:
            texto = (titulo + "\n" if titulo else "") + "\n".join(buffer).strip()
            bloques.append((relativo, inicio, texto))

    for numero, linea in enumerate(lineas, start=1):
        if linea.startswith("#"):
            cerrar()
            buffer = []
            titulo = linea.strip("# ").strip()
            inicio = numero
            continue
        if not linea.strip():
            cerrar()
            buffer = []
            inicio = numero + 1
            continue
        if not buffer:
            inicio = numero
        buffer.append(linea)
    cerrar()
    return bloques


def _documentos() -> list[tuple[str, int, str]]:
    """Fragmentos de todos los documentos, leídos una sola vez por proceso."""
    if _CACHE["documentos"] is None:
        _CACHE["documentos"] = _fragmentos()
    return _CACHE["documentos"]


def _frecuencias() -> dict[str, int]:
    """En cuántos fragmentos aparece cada término (para pesar lo raro)."""
    if _CACHE["frecuencias"] is None:
        tabla: dict[str, int] = {}
        for _, _, texto in _documentos():
            for termino in set(_terminos(texto)):
                tabla[termino] = tabla.get(termino, 0) + 1
        _CACHE["frecuencias"] = tabla
    return _CACHE["frecuencias"]


def buscar(pregunta: str, maximo: int = MAX_FRAGMENTOS) -> list[dict]:
    """Fragmentos del repositorio que mejor responden a la pregunta.

    Puntuación léxica con peso por rareza: lo que aparece en pocos fragmentos
    (por ejemplo «cuadra» o «instantánea») decide más que lo que sale en todas
    partes. El README y las decisiones pesan un poco más, porque son la
    documentación de entrada del proyecto.
    """
    terminos = _terminos(pregunta)
    if not terminos:
        return []
    documentos = _documentos()
    frecuencias = _frecuencias()
    total = max(len(documentos), 1)
    frase = _sin_acentos(" ".join(terminos))
    puntuados: list[tuple[float, str, int, str]] = []
    for fichero, linea, texto in documentos:
        plano = _sin_acentos(texto.lower())
        plano_fichero = _sin_acentos(fichero.lower())
        puntos = 0.0
        for termino in terminos:
            apariciones = plano.count(termino)
            cola = 0
            if len(termino) >= 6:
                cola = max(plano.count(termino[:6]) - apariciones, 0)
            if not apariciones and not cola:
                continue
            rareza = 1 + (total / (1 + frecuencias.get(termino, 1))) ** 0.5
            puntos += (1 + apariciones ** 0.5) * rareza
            puntos += cola * 0.35 * rareza  # singulares y plurales, casi la misma palabra
            if termino in plano_fichero:
                puntos += 3
        if puntos:
            if fichero.split("/")[0] in ("README.md", "DECISIONS.md", "SECURITY.md"):
                puntos *= 1.4
            if frase and frase in _sin_acentos(plano):
                puntos += 10
            puntuados.append((puntos, fichero, linea, texto))
    puntuados.sort(key=lambda fila: (-fila[0], fila[1], fila[2]))
    return [
        {"fichero": fichero, "linea": linea, "texto": texto}
        for _, fichero, linea, texto in puntuados[:maximo]
    ]


def _clave() -> str:
    for variable in ("MUEBLES_LLM_KEY", "OPENROUTER_API_KEY"):
        valor = os.environ.get(variable, "").strip()
        if valor:
            return valor
    for candidato in FICHEROS_CLAVE:
        try:
            contenido = Path(candidato).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for linea in contenido.splitlines():
            if linea.startswith("OPENROUTER_API_KEY="):
                valor = linea.split("=", 1)[1].strip().strip('"').strip("'")
                if valor:
                    return valor
    return ""


def _redactar(pregunta: str, fragmentos: list[dict]) -> tuple[str, str]:
    clave = _clave()
    if not clave:
        return "", "sin-clave"
    contexto = "\n\n".join(f"[{f['fichero']}:{f['linea']}]\n{f['texto']}" for f in fragmentos)
    cuerpo = json.dumps({
        "model": MODELO_POR_DEFECTO,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": f"Fragmentos del repositorio:\n\n{contexto}\n\nPregunta: {pregunta}"},
        ],
    }).encode("utf-8")
    peticion = urllib.request.Request(
        URL_MODELO, data=cuerpo,
        headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=45) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        return datos["choices"][0]["message"]["content"].strip(), "modelo"
    except Exception:  # noqa: BLE001  (si el modelo falla, se dice; no se inventa)
        return "", "modelo-fallo"


def responder(pregunta: str) -> dict:
    """Respuesta del asistente: texto, fuentes y de dónde sale el texto."""
    pregunta = (pregunta or "").strip()
    if len(pregunta) < 4:
        return {"respuesta": "Escribe una pregunta sobre el proyecto.", "fuentes": [], "origen": "vacio"}
    fragmentos = buscar(pregunta)
    if not fragmentos:
        return {
            "respuesta": "No encuentro nada de eso en la documentación del proyecto.",
            "fuentes": [], "origen": "sin-fragmentos",
        }
    texto, origen = _redactar(pregunta, fragmentos)
    fuentes = [f"{f['fichero']}:{f['linea']}" for f in fragmentos]
    if origen == "modelo":
        return {"respuesta": texto, "fuentes": fuentes, "origen": origen}
    if origen == "sin-clave":
        aviso = ("Sin clave de modelo configurada: te enseño los fragmentos exactos del "
                 "repositorio que responden a tu pregunta, sin redactar nada por mi cuenta.")
    else:
        aviso = ("El modelo no respondió; te enseño los fragmentos exactos del repositorio "
                 "que responden a tu pregunta.")
    recorte = fragmentos[0]["texto"].strip().splitlines()[:12]
    return {
        "respuesta": aviso + "\n\n" + "\n".join(recorte),
        "fuentes": fuentes,
        "origen": origen,
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(responder(" ".join(sys.argv[1:])), ensure_ascii=False, indent=2))
