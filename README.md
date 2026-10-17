# Manual de Instalación y Configuración: Quiosco de Impresión DeCA / e-CMR

Sistema autónomo desatendido para la lectura de códigos QR DeCA (Documento Electrónico de Control Administrativo para el transporte en España) y expedición automática de documentos PDF en almacén.

---

## 1. Componentes del Hardware

| Componente | Modelo / Especificación | Función |
| :--- | :--- | :--- |
| **SBC (Placa)** | Orange Pi Zero (Allwinner H2+ / H3, 512 MB RAM) | Procesador central y controlador de red |
| **Almacenamiento** | MicroSD 8 GB a 32 GB (Clase 10 / UHS-I / A1) | Sistema operativo y configuración local |
| **Lector QR / 2D** | Approx appLS20DESK+ (USB HID) | Escaneo omnidireccional de códigos QR de conductores |
| **Impresora** | Kyocera ECOSYS P2040dn (Conexión Ethernet) | Impresión láser del albarán/carta de porte |
| **Alimentación** | Fuente estabilizada 5V DC / 2.5A – 3A | Suministro eléctrico de placa y escáner USB |

---

## 2. Esquema de Conexiones Físicas

1. **Red Local:**
   * Conectar la **Orange Pi Zero** al switch/router mediante cable RJ45.
   * Conectar la **Kyocera ECOSYS P2040dn** a la misma subred mediante cable RJ45.
2. **Lector de Códigos Approx:**
   * Conectar directamente al puerto hembra USB Tipo A de la Orange Pi Zero.
3. **Alimentación Eléctrica (Opciones):**
   * **Conector Micro-USB (Recomendada):** Conectar un cable micro-USB desde la fuente de 5V 3A al conector lateral de la placa.
   * **Pines GPIO (Directo):**
     * Positivo (+5V): Pin 2 o Pin 4 de la cabecera principal de 26 pines (fila inferior exterior).
     * Negativo (GND): Pin 6 de la cabecera principal de 26 pines.

---

## 3. Preparación del Sistema Operativo

1. Descargar la imagen oficial **Armbian CLI / Server** (basada en Debian Bookworm o Ubuntu Jammy) para *Orange Pi Zero* desde [armbian.com/orange-pi-zero/](https://www.armbian.com/orange-pi-zero/).
2. Grabar la imagen en la tarjeta MicroSD usando **BalenaEtcher** o **Raspberry Pi Imager**.
3. Insertar la tarjeta en la ranura MicroSD de la placa y conectar la alimentación y el cable de red.
4. Conectarse vía SSH desde el terminal del ordenador:
   ```bash
   ssh root@orangepizero.local
   # Contraseña por defecto: 1234
   ```
5. Completar el asistente inicial de cambio de contraseña y configuración horaria (`Europe/Madrid`).

---

## 4. Instalación de Paquetes y Dependencias

Ejecutar en la Orange Pi los siguientes comandos para actualizar el sistema e instalar el servidor de impresión CUPS y las librerías necesarias:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y cups cups-client printer-driver-all foomatic-db-compressed-ppds python3 python3-requests python3-evdev
```

---

## 5. Configuración de la Impresora en CUPS

Identificar la IP estática asignada a la Kyocera (ejemplo: `192.168.1.176`).

1. Registrar la impresora en CUPS mediante conexión IPP estándar:
   ```bash
   sudo lpadmin -p Kyocera_Sucs -E -v ipp://192.168.1.176/ipp/print -m everywhere
   sudo lpoptions -d Kyocera_Sucs
   ```

   *(Alternativa si se prefiere Socket RAW directo puerto 9100 con driver PostS
   cript):*
   ```bash
   sudo lpadmin -p Kyocera_Sucs -E -v socket://192.168.1.176:9100 -m lsb/usr/cupsfilters/Generic-PostScript_Printer-Postscript.ppd
   sudo lpoptions -d Kyocera_Sucs
   ```

2. Comprobar el estado y realizar una impresión de prueba:
   ```bash
   lpstat -p Kyocera_Sucs -d
   echo "Prueba de impresion quiosco DeCA" | lp
   ```

---

## 6. Script de Impresión Automática y Reporte de Errores

Crear el script en `/usr/local/bin/deca_printer.py`:

```bash
sudo nano /usr/local/bin/deca_printer.py
```

Pegar el siguiente contenido:

```python
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

# Mapeo de teclas para escáneres USB que emulan teclado
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
    'KEY_MINUS': ('-', '_'),
    'KEY_SLASH': ('/', '?'),
    'KEY_DOT': ('.', ':'),
    'KEY_SEMICOLON': (';', ':'),
    'KEY_EQUAL': ('=', '+'),
    'KEY_COMMA': (',', ';'),
    'KEY_QUESTION': ('?', '?'),
}

def imprimir_error(mensaje, url=None):
    """Expide una hoja impresa cuando ocurre un error en el quiosco sin pantalla."""
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

    print(f"[!] Generando reporte de error impreso...", flush=True)
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
    # Corrección de seguridad para variaciones de teclado en dominios habituales
    if "e/cmr.services" in url:
        url = url.replace("e/cmr.services", "e-cmr.services")

    print(f"[*] Descargando documento: {url}", flush=True)
    temp_path = None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 401:
            imprimir_error("ERROR HTTP 401: Acceso no autorizado / Requiere credenciales.", url)
            return
        elif response.status_code != 200:
            imprimir_error(f"ERROR HTTP {response.status_code}: El servidor no entrego el PDF.", url)
            return

        # Almacenamiento en RAM (/dev/shm) para alargar la vida util de la MicroSD
        with tempfile.NamedTemporaryFile(dir="/dev/shm", suffix=".pdf", delete=False) as f:
            f.write(response.content)
            temp_path = f.name

        subprocess.run(["lp", "-o", "fit-to-page", temp_path], check=True)
        print("[+] Documento impreso con exito.", flush=True)

    except requests.exceptions.RequestException as e:
        imprimir_error(f"Error de conexion de red: {e}", url)
    except Exception as e:
        imprimir_error(f"Error en cola de impresion: {e}", url)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def main():
    dev = get_reader_device()
    if not dev:
        print("[!] Lector de codigos USB no detectado.", flush=True)
        sys.exit(1)

    print(f"[*] Escuchando lector en: {dev.name} ({dev.path})", flush=True)
    buffer = ""
    shift_pressed = False

    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY:
            data = categorize(event)
            if data.keystate == 1:  # Tecla pulsada
                code = data.keycode
                if "SHIFT" in code:
                    shift_pressed = True
                    continue
                if code == 'KEY_ENTER':
                    match = URL_PATTERN.search(buffer)
                    if match:
                        imprimir_pdf(match.group(0))
                    else:
                        print(f"[!] Lectura no valida: {buffer}", flush=True)
                        imprimir_error(f"El codigo escaneado no es una URL valida:\n{buffer}")
                    buffer = ""
                elif code in CHAR_MAP:
                    normal_char, shifted_char = CHAR_MAP[code]
                    buffer += shifted_char if shift_pressed else normal_char
            elif data.keystate == 0:  # Tecla liberada
                if "SHIFT" in data.keycode:
                    shift_pressed = False

if __name__ == "__main__":
    main()
```

Asignar permisos de ejecución al script:
```bash
sudo chmod +x /usr/local/bin/deca_printer.py
```

---

## 7. Configuración del Servicio Automático (Systemd)

Para que el script se inicie automáticamente en cada encendido sin requerir inicio de sesión:

1. Crear el archivo de unidad `/etc/systemd/system/deca-printer.service`:
   ```bash
   sudo nano /etc/systemd/system/deca-printer.service
   ```

2. Añadir la siguiente configuración:
   ```ini
   [Unit]
   Description=Quiosco Lector DeCA e Impresion Automatica
   After=network.target cups.service

   [Service]
   Type=simple
   User=root
   ExecStart=/usr/bin/python3 -u /usr/local/bin/deca_printer.py
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```

3. Registrar e iniciar el servicio:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now deca-printer.service
   ```

---

## 8. Monitorización y Mantenimiento

* **Ver registros de escaneo en directo:**
  ```bash
  sudo journalctl -u deca-printer.service -f
  ```
* **Comprobar estado del servicio:**
  ```bash
  sudo systemctl status deca-printer.service
  ```
* **Reiniciar servicio tras modificaciones:**
  ```bash
  sudo systemctl restart deca-printer.service
  ```
* **Comprobar cola de trabajos de impresión:**
  ```bash
  lpstat -o
  ```