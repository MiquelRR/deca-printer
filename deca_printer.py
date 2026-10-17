#!/usr/bin/env python3
import os
import re
import sys
import tempfile
import subprocess
import datetime
import requests
import evdev
from evdev import InputDevice, categorize, ecodes

URL_PATTERN = re.compile(r'https?://[^\s]+')

# Mapa de caracteres para escáneres en modo emulación teclado
# Cubre minúsculas, mayúsculas y caracteres típicos en URLs
CHAR_MAP = {
    'KEY_0': ('0', '0'), 'KEY_1': ('1', '1'), 'KEY_2': ('2', '2'),
    'KEY_3': ('3', '3'), 'KEY_4': ('4', '4'), 'KEY_5': ('5', '5'),
    'KEY_6': ('6', '6'), 'KEY_7': ('7', '/'), 'KEY_8': ('8', '('),
    'KEY_9': ('9', ')'),
    'KEY_A': ('a', 'A'), 'KEY_B': ('b', 'B'), 'KEY_C': ('c', 'C'),
    'KEY_D': ('d', 'D'), 'KEY_E': ('e', 'E'), 'KEY_F': ('f', 'F'),
    'KEY_G': ('g', 'G'), 'KEY_H': ('h', 'H'), 'KEY_I': ('i', 'I'),
    'KEY_J': ('j', 'J'), 'KEY_K': ('k', 'K'), 'KEY_L': ('l', 'L'),
    'KEY_M': ('m', 'M'), 'KEY_N': ('n', 'N'), 'KEY_O': ('o', 'O'),
    'KEY_P': ('p', 'P'), 'KEY_Q': ('q', 'Q'), 'KEY_R': ('r', 'R'),
    'KEY_S': ('s', 'S'), 'KEY_T': ('t', 'T'), 'KEY_U': ('u', 'U'),
    'KEY_V': ('v', 'V'), 'KEY_W': ('w', 'W'), 'KEY_X': ('x', 'X'),
    'KEY_Y': ('y', 'Y'), 'KEY_Z': ('z', 'Z'),
    # Teclas de puntuación (según disposición de teclado habitual)
    'KEY_MINUS': ('-', '_'),
    'KEY_SLASH': ('/', '?'),
    'KEY_DOT': ('.', ':'),
    'KEY_SEMICOLON': (';', ':'),
    'KEY_EQUAL': ('=', '+'),
    'KEY_COMMA': (',', ';'),
    'KEY_QUESTION': ('?', '?'),
}

def imprimir_error(mensaje, url=None):
    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    reporte = (
        "========================================\n"
        "      ERROR SISTEMA IMPRESION DeCA      \n"
        "========================================\n\n"
        f"Fecha/Hora : {ahora}\n"
        f"Incidencia : {mensaje}\n"
    )
    if url:
        reporte += f"URL leida  : {url}\n"
    reporte += "\n----------------------------------------\n"
    reporte += "Por favor, notifique al responsable de IT.\n"
    reporte += "========================================\n"

    print(f"[!] Imprimiendo reporte de error...", flush=True)
    try:
        proc = subprocess.Popen(["lp", "-o", "cpi=12", "-o", "lpi=6"], stdin=subprocess.PIPE)
        proc.communicate(input=reporte.encode('utf-8'))
    except Exception as e:
        print(f"[!] No se pudo imprimir el reporte de error: {e}", flush=True)

def get_reader_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for dev in devices:
        name = dev.name.lower()
        if "keyboard" in name or "barcode" in name or "scanner" in name or "tms" in name:
            return dev
    if devices:
        return devices[0]
    return None

def imprimir_pdf(url):
    # Corrección de seguridad para dominios e-cmr si la tecla guión llegó rota
    if "e/cmr.services" in url:
        url = url.replace("e/cmr.services", "e-cmr.services")

    print(f"[*] Descargando: {url}", flush=True)
    temp_path = None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            imprimir_error(f"ERROR HTTP {response.status_code}: Servidor no devolvio el documento.", url)
            return

        with tempfile.NamedTemporaryFile(dir="/dev/shm", suffix=".pdf", delete=False) as f:
            f.write(response.content)
            temp_path = f.name

        subprocess.run(["lp", "-o", "fit-to-page", temp_path], check=True)
        print("[+] Documento impreso con exito.", flush=True)

    except requests.exceptions.RequestException as e:
        imprimir_error(f"Error de conexion al descargar: {e}", url)
    except Exception as e:
        imprimir_error(f"Fallo en proceso de impresion: {e}", url)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def main():
    dev = get_reader_device()
    if not dev:
        print("[!] No se encontro lector USB conectado.", flush=True)
        sys.exit(1)

    print(f"[*] Escuchando lector en: {dev.name} ({dev.path})", flush=True)
    buffer = ""
    shift_pressed = False

    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY:
            data = categorize(event)
            if data.keystate == 1:  # Key Down
                code = data.keycode
                if "SHIFT" in code:
                    shift_pressed = True
                    continue
                if code == 'KEY_ENTER':
                    match = URL_PATTERN.search(buffer)
                    if match:
                        imprimir_pdf(match.group(0))
                    else:
                        print(f"[!] Formato no valido: {buffer}", flush=True)
                        imprimir_error(f"Codigo leido no contiene URL valida:\n{buffer}")
                    buffer = ""
                elif code in CHAR_MAP:
                    normal_char, shifted_char = CHAR_MAP[code]
                    buffer += shifted_char if shift_pressed else normal_char
                else:
                    # Si llega una tecla no mapeada, imprimir en consola para depurarla
                    print(f"[Debug] Tecla no mapeada: {code}", flush=True)

            elif data.keystate == 0:  # Key Up
                if "SHIFT" in data.keycode:
                    shift_pressed = False

if __name__ == "__main__":
    main()