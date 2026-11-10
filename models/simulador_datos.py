"""Datos coherentes de la empresa simulada (lógica pura, sin Odoo).

Muebles del Hogar S.L. está en Castelló y vende sobre todo en la Comunitat
Valenciana, con algún cliente de contract en otras ciudades. Aquí viven las
reglas que dan a cada contacto una dirección, provincia, NIF y teléfono que
casan entre sí y con su nombre. Todo es determinista: el mismo contacto recibe
siempre los mismos datos, y una segunda pasada no cambia nada.
"""
from __future__ import annotations

import hashlib
import re

URL_PUBLICA = 'https://odoocrm.kavanasystems.com'
ZONA_HORARIA = 'Europe/Madrid'

# ciudad: (código de provincia en Odoo, prefijo del código postal, prefijo telefónico)
CIUDADES = {
    'Castelló de la Plana': ('CS', '120', '964'),
    'Vila-real': ('CS', '125', '964'),
    'Segorbe': ('CS', '124', '964'),
    'Vinaròs': ('CS', '125', '964'),
    'València': ('V', '460', '963'),
    'Alzira': ('V', '466', '962'),
    'Sagunt': ('V', '465', '962'),
    'Gandia': ('V', '467', '962'),
    'Alacant': ('A', '030', '965'),
    'Elda': ('A', '036', '966'),
    'Oriola': ('A', '033', '966'),
    'Barcelona': ('B', '080', '93'),
    'Madrid': ('M', '280', '91'),
    'Sevilla': ('SE', '410', '954'),
}
# Pistas en el nombre del contacto -> ciudad. La primera que aparece manda.
PISTAS = (
    (r'barcelona', 'Barcelona'), (r'madrid', 'Madrid'), (r'sevilla|\bsur\b', 'Sevilla'),
    (r'alacant|alicante', 'Alacant'), (r'vinalop', 'Elda'), (r'segura', 'Oriola'),
    (r'alzira|ribera', 'Alzira'), (r'segorbe|palanc', 'Segorbe'), (r'maestrat|vinar', 'Vinaròs'),
    (r'vila-?real', 'Vila-real'), (r'sagunt', 'Sagunt'), (r'gandia', 'Gandia'),
    (r'val[eè]ncia|turia|x[uú]quer|levante|alboraya', 'València'),
    (r'castell[oó]|la plana', 'Castelló de la Plana'),
)
POR_DEFECTO = ('Castelló de la Plana', 'València', 'Vila-real', 'Alacant')
CALLES = ('Carrer Major', 'Avinguda del Mar', 'Carrer de Sant Vicent', 'Polígon Industrial El Collet',
          'Avinguda de València', 'Carrer de la Mar', 'Carrer del Comerç', 'Ronda Mijares',
          'Calle Mayor', 'Avenida de la Constitución', 'Polígono Industrial Las Atalayas')
PALABRAS_DE_EMPRESA = re.compile(
    r'\b(s\.?\s?l\.?u?|s\.?\s?a\.?|s\.?\s?coop|grup|grupo|constructora|promotora|hotel|restaurante|'
    r'residencial|residencia|estudi|estudio|interiors?|interiorismo|reformas|apartamentos|coworking|'
    r'cl[ií]nica|colegio|club|contract|mobiliari|mobles|muebles|decoraci[oó]|disseny|habitatges?|'
    r'tapisseria|fusteria|cadena|despachos|casa|llar|espai|distribucions?)\b', re.I)
# Marcas de los datos de ejemplo de Odoo que no pegan en una pyme de Castelló.
RENOMBRAR = {'Trelian': 'Grupo Trelles', 'DeltaPC': 'Delta Oficines'}
LETRAS_CIF = 'JABCDEFGHI'
LETRAS_NIF = 'TRWAGMYFPDXBNJZSQVHLCKE'


def _numero(semilla: str, digitos: int) -> int:
    return int(hashlib.sha256(semilla.encode()).hexdigest(), 16) % (10 ** digitos)


def ciudad_para(nombre: str, semilla: str) -> str:
    texto = (nombre or '').lower()
    for patron, ciudad in PISTAS:
        if re.search(patron, texto):
            return ciudad
    return POR_DEFECTO[_numero(semilla, 4) % len(POR_DEFECTO)]


def direccion(nombre: str, semilla: str) -> dict:
    ciudad = ciudad_para(nombre, semilla)
    provincia, cp, prefijo = CIUDADES[ciudad]
    n = _numero(semilla + '/dir', 6)
    return {
        'street': f'{CALLES[n % len(CALLES)]}, {n % 120 + 1}',
        'city': ciudad,
        'zip': f'{cp}{n % 100:02d}',
        'provincia': provincia,
        'phone': telefono_fijo(prefijo, semilla),
    }


def telefono_fijo(prefijo: str, semilla: str) -> str:
    resto = str(_numero(semilla + '/tel', 9 - len(prefijo))).zfill(9 - len(prefijo))
    numero = prefijo + resto
    return f'+34 {numero[:3]} {numero[3:6]} {numero[6:]}'


def movil(semilla: str) -> str:
    n = str(_numero(semilla + '/movil', 8)).zfill(8)
    return f'+34 6{n[:2]} {n[2:5]} {n[5:]}'


def es_telefono_espanol(telefono: str | None) -> bool:
    return not telefono or telefono.replace(' ', '').startswith('+34')


def telefono_de_relleno(telefono: str | None) -> bool:
    """Los de la carga inicial: «+34 600 007 007», a la vista que son de mentira."""
    return bool(re.fullmatch(r'\+34 600 0(\d\d) 0\1', (telefono or '').strip()))


def cif(semilla: str) -> str:
    """CIF de sociedad limitada (B) con su control válido, en el formato de Odoo 20 (ES…)."""
    cuerpo = str(_numero(semilla + '/cif', 7)).zfill(7)
    return f'ESB{cuerpo}{_control_cif(cuerpo)}'


def cif_valido(valor: str | None) -> bool:
    m = re.fullmatch(r'(?:ES)?B(\d{7})(\d)', valor or '')
    return bool(m) and _control_cif(m.group(1)) == int(m.group(2))


def _control_cif(cuerpo: str) -> int:
    pares = sum(int(c) for c in cuerpo[1::2])
    impares = sum(sum(divmod(int(c) * 2, 10)) for c in cuerpo[0::2])
    return (10 - (pares + impares) % 10) % 10


def nif(semilla: str) -> str:
    """NIF de persona con su letra válida."""
    numero = _numero(semilla + '/nif', 8)
    return f'ES{numero:08d}{LETRAS_NIF[numero % 23]}'


def parece_empresa(nombre: str | None) -> bool:
    return bool(PALABRAS_DE_EMPRESA.search(nombre or ''))


def empresa_del_titulo(titulo: str | None) -> str:
    """«Presupuesto de 25 mesas — Contract Habitat» -> «Contract Habitat»."""
    _, guion, cola = (titulo or '').partition(' — ')
    return cola.strip() if guion else ''


def renombrar(texto: str | None) -> str:
    resultado = texto or ''
    for viejo, nuevo in RENOMBRAR.items():
        resultado = re.sub(rf'\b{re.escape(viejo)}\b', nuevo, resultado)
    return resultado


def parece_ingles(texto: str | None) -> bool:
    """Descripciones heredadas del catálogo en inglés («Tufted Gallery Bench…»).

    La referencia interna entre corchetes («[console-table-umber]») se ignora:
    es un código, y está en inglés también en las líneas ya traducidas.
    """
    sin_referencia = re.sub(r'\[[^\]]*\]', '', texto or '')
    return bool(re.search(r'\b(the|with|and|this|chair|table|bench|stool|made|piece)\b',
                          sin_referencia, re.I))
