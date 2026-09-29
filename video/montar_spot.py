#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monta el spot de 20-30 s del laboratorio de muebles a partir de capturas reales.

Escenas: landing, tienda, CRM, panel del día y cierre. Cada escena lleva un
zoom o un desplazamiento suave, su rótulo y su locución. Los tiempos se calculan
a partir de la locución (no al revés): la escena dura lo que dura su frase más
un respiro.

Todo con ffmpeg + PIL, reejecutable: cambia un rótulo o una duración y se vuelve
a lanzar este script.
"""
import os
import subprocess
import sys

BASE = '/root/.hermes/profiles/hermes2/ODOO_CRM/video'
CAPTURAS = os.path.join(BASE, 'capturas')
SEGMENTOS = os.path.join(BASE, 'segmentos')
FINAL = os.path.join(BASE, 'spot-muebles-kavana.mp4')
FUENTE_TITULO = '/usr/share/fonts/truetype/lato/Lato-Bold.ttf'
FUENTE_TEXTO = '/usr/share/fonts/truetype/lato/Lato-Regular.ttf'
NARANJA = '0xff7020'
FONDO = '0x0a0a0f'
FPS = 25
ANCHO, ALTO = 1920, 1080

os.makedirs(SEGMENTOS, exist_ok=True)


def duracion(ruta):
    salida = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', ruta],
        capture_output=True, text=True, check=True)
    return float(salida.stdout.strip())


def escribir_texto(nombre, texto):
    ruta = os.path.join(SEGMENTOS, nombre + '.txt')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)
    return ruta


# ---------------------------------------------------------------- tarjeta final
def tarjeta_cierre():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (ANCHO, ALTO), (10, 10, 15))
    dib = ImageDraw.Draw(img)
    # halo naranja arriba
    for i in range(220, 0, -1):
        alpha = int(26 * (i / 220) ** 2)
        dib.ellipse([ANCHO / 2 - 900 - i, -700 - i, ANCHO / 2 + 900 + i, 500 + i],
                    outline=None, fill=(10 + alpha, 10 + int(alpha * 0.45), 15))
    fuente_marca = ImageFont.truetype(FUENTE_TITULO, 118)
    fuente_titulo = ImageFont.truetype(FUENTE_TITULO, 64)
    fuente_texto = ImageFont.truetype(FUENTE_TEXTO, 32)
    # marca
    dib.rounded_rectangle([ANCHO / 2 - 62, 300, ANCHO / 2 + 62, 424], radius=26, fill=(255, 112, 32))
    dib.text((ANCHO / 2, 360), "MH", font=fuente_marca, fill=(12, 12, 18), anchor="mm")
    dib.text((ANCHO / 2, 520), "Muebles del Hogar S.L.", font=fuente_titulo, fill=(240, 240, 245), anchor="mm")
    dib.text((ANCHO / 2, 590), "Laboratorio Odoo 17 · empresa ficticia, datos de ejemplo",
             font=fuente_texto, fill=(144, 144, 168), anchor="mm")
    # regla naranja
    dib.rectangle([ANCHO / 2 - 60, 660, ANCHO / 2 + 60, 665], fill=(255, 112, 32))
    dib.text((ANCHO / 2, 730), "muebles.kavanasystems.com", font=fuente_titulo, fill=(255, 112, 32), anchor="mm")
    dib.text((ANCHO / 2, 800), "Kavana Systems · proyecto de demostración",
             font=fuente_texto, fill=(96, 96, 120), anchor="mm")
    ruta = os.path.join(BASE, 'cierre.png')
    img.save(ruta)
    print("tarjeta de cierre:", ruta, os.path.getsize(ruta), "bytes")
    return ruta


# ---------------------------------------------------------------- escenas
ESCENAS = [
    dict(nombre='01_landing', imagen=os.path.join(CAPTURAS, 'landing_hero.png'),
         narracion='narracion_1.ogg', respiro=1.2,
         titulo='Una empresa de muebles, entera, sobre Odoo 17',
         subtitulo='Laboratorio de demostración · Kavana Systems',
         movimiento='zoom'),
    dict(nombre='02_tienda', imagen=os.path.join(CAPTURAS, 'tienda.png'),
         narracion='narracion_2.ogg', respiro=1.1,
         titulo='80 muebles reales, en español y en euros',
         subtitulo='Tienda publicada · IVA 21 % · precios en formato español',
         movimiento='zoom_arriba'),
    dict(nombre='03_crm', imagen=os.path.join(CAPTURAS, 'crm_kanban.png'),
         narracion='narracion_3.ogg', respiro=1.1,
         titulo='Ventas, compras y almacén',
         subtitulo='CRM en español · 56 pedidos de venta · 11 de compra',
         movimiento='izquierda'),
    dict(nombre='04_panel', imagen=os.path.join(CAPTURAS, 'panel_dia.png'),
         narracion='narracion_4.ogg', respiro=1.1,
         titulo='Y un panel que dice qué toca hoy',
         subtitulo='2.190 unidades cuadradas con el libro · diferencia 0',
         movimiento='abajo'),
]


def filtro(escena, segundos):
    fotogramas = max(int(round(segundos * FPS)), 1)
    if escena['movimiento'] == 'zoom':
        zoom = "min(1.0+0.0016*on,1.12)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif escena['movimiento'] == 'zoom_arriba':
        zoom = "min(1.0+0.0014*on,1.10)"
        x = "iw/2-(iw/zoom/2)"
        y = "0"
    elif escena['movimiento'] == 'izquierda':
        zoom = "min(1.0+0.0022*on,1.16)"
        x = "max(iw/2-(iw/zoom/2)-on*2.2,0)"
        y = "ih/2-(ih/zoom/2)"
    else:  # abajo
        zoom = "1.30"
        x = "iw/2-(iw/zoom/2)"
        y = "(ih-ih/1.30)*min(on/%d,1)" % max(fotogramas - 1, 1)

    cadena = [
        f"scale={ANCHO*2}:-2",
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={fotogramas}:s={ANCHO}x{ALTO}:fps={FPS}",
        "format=yuv420p",
        f"drawbox=x=0:y=900:w={ANCHO}:h=180:color={FONDO}@0.82:t=fill",
        f"drawbox=x=64:y=926:w=6:h=58:color={NARANJA}@0.95:t=fill",
        "drawtext=fontfile=%s:textfile=%s:fontcolor=white:fontsize=%d:x=96:y=928:"
        "alpha='if(lt(t,0.7),t/0.7,1)'" % (FUENTE_TITULO, escena['titulo_txt'], 44),
        "drawtext=fontfile=%s:textfile=%s:fontcolor=0xc8c8d6:fontsize=%d:x=98:y=986:"
        "alpha='if(lt(t,1.0),t/1.0,1)'" % (FUENTE_TEXTO, escena['subtitulo_txt'], 27),
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={max(segundos - 0.4, 0.1):.2f}:d=0.4",
    ]
    return ",".join(cadena)


def construir():
    tarjeta = tarjeta_cierre()
    ESCENAS.append(dict(nombre='05_cierre', imagen=tarjeta, narracion='narracion_5.ogg',
                        respiro=1.3, titulo='', subtitulo='', movimiento='zoom'))

    listado = []
    total = 0.0
    for escena in ESCENAS:
        nar = os.path.join(BASE, escena['narracion'])
        voz = duracion(nar)
        segundos = round(voz + escena['respiro'], 2)
        total += segundos
        escena['titulo_txt'] = escribir_texto(escena['nombre'] + '_titulo', escena['titulo']) if escena['titulo'] else None
        escena['subtitulo_txt'] = escribir_texto(escena['nombre'] + '_sub', escena['subtitulo']) if escena['subtitulo'] else None
        print("%s: voz %.2f s + respiro %.2f = %.2f s" % (escena['nombre'], voz, escena['respiro'], segundos))

        cadena = filtro(escena, segundos) if escena['titulo'] else \
            f"scale={ANCHO*2}:-2,zoompan=z='min(1.0+0.0010*on,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(segundos*FPS)}:s={ANCHO}x{ALTO}:fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={max(segundos-0.5,0.1):.2f}:d=0.5"

        salida = os.path.join(SEGMENTOS, escena['nombre'] + '.mp4')
        orden = [
            'ffmpeg', '-y', '-loop', '1', '-i', escena['imagen'], '-i', nar,
            '-filter_complex', f"[0:v]{cadena}[v];[1:a]adelay=600|600,apad,aresample=48000[a]",
            '-map', '[v]', '-map', '[a]', '-t', str(segundos),
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-r', str(FPS), '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2',
            salida,
        ]
        resultado = subprocess.run(orden, capture_output=True, text=True)
        if resultado.returncode != 0:
            print("FALLO en", escena['nombre'])
            print(resultado.stderr[-2500:])
            sys.exit(1)
        print("   segmento listo:", escena['nombre'], "%.2f s" % duracion(salida))
        listado.append(salida)

    with open(os.path.join(SEGMENTOS, 'lista.txt'), 'w', encoding='utf-8') as f:
        for ruta in listado:
            f.write("file '%s'\n" % ruta)

    resultado = subprocess.run(
        ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', os.path.join(SEGMENTOS, 'lista.txt'),
         '-c', 'copy', FINAL], capture_output=True, text=True)
    if resultado.returncode != 0:
        print("FALLO al unir:", resultado.stderr[-2000:])
        sys.exit(1)
    print("\nv\u00eddeo final:", FINAL)
    print("duraci\u00f3n declarada por suma de escenas: %.2f s" % total)
    print("duraci\u00f3n real del fichero: %.2f s" % duracion(FINAL))
    print("tama\u00f1o: %.1f MB" % (os.path.getsize(FINAL) / 1024 / 1024))


if __name__ == '__main__':
    construir()
