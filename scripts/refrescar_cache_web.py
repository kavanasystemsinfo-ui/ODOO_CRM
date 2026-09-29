#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresca la cache del Odoo en marcha escribiendo desde dentro, por XML-RPC.

Por que: la ficha de la web quedo cacheada en el proceso servidor con la lista
de idiomas vieja (solo en_US). Un cambio por SQL desde fuera NO invalida esa
cache; una escritura por XML-RPC si, porque ocurre dentro del propio servidor.

Las credenciales se leen del fichero del perfil y no se imprimen nunca.
"""
import re
import xmlrpc.client

FICHERO = "/root/.hermes/profiles/hermes2/credenciales_muebles_lab.txt"

datos = {}
for linea in open(FICHERO, encoding="utf-8"):
    if ":" in linea:
        etiqueta, valor = linea.split(":", 1)
        datos[etiqueta.strip().lower()] = valor.strip()

url = datos["url"]
base = datos["base de datos"]
usuario = datos["usuario"]
clave = datos["contraseña"]

comun = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % url)
uid = comun.authenticate(base, usuario, clave, {})
print("autenticado como uid", uid, "en", base)

modelos = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % url)


def llamar(modelo, metodo, args, kwargs=None):
    return modelos.execute_kw(base, uid, clave, modelo, metodo, args, kwargs or {})


idiomas = llamar("res.lang", "search_read", [[["code", "=", "es_ES"]]], {"fields": ["id", "code"], "context": {"active_test": False}})
es_id = idiomas[0]["id"]
print("es_ES id:", es_id)

webs = llamar("website", "search_read", [[]], {"fields": ["id", "name", "default_lang_id", "language_ids"]})
print("webs antes:", webs)

for web in webs:
    llamar("website", "write", [[web["id"]], {"default_lang_id": es_id, "language_ids": [(6, 0, [es_id])]}])
    print("web %s escrita" % web["id"])

webs = llamar("website", "search_read", [[]], {"fields": ["id", "name", "default_lang_id", "language_ids"]})
print("webs despues:", webs)
print("LISTO: la cache del servidor queda invalidada y la lista de idiomas es la correcta")
