import time
import os
import socket
import threading
import signal
import sys
import pytz
from datetime import datetime
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

ROME = pytz.timezone("Europe/Rome")

serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

with canvas(device) as draw:
    draw.text((10, 10), "IU5MGF-10", fill="white")
    draw.text((5, 25), "Server RPi5", fill="white")
    draw.text((15, 40), "Avvio...", fill="white")
time.sleep(3)

# stato condiviso
state = {
    "temp": "N/D",
    "ssd": "N/D",
    "ip": "N/D",
    "time": "--:--",
    "blink": False
}

def shutdown(signum, frame):
    device.clear()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "N/D"

def update_data():
    while True:
        try:
            temp_raw = open("/sys/class/thermal/thermal_zone0/temp").read().strip()
            state["temp"] = f"{int(temp_raw)/1000:.1f}C"
        except:
            state["temp"] = "N/D"
        try:
            st = os.statvfs("/mnt/ssd")
            disk_total = st.f_blocks * st.f_frsize // (1024**3)
            disk_free = st.f_bavail * st.f_frsize // (1024**3)
            disk_used = disk_total - disk_free
            disk_perc = round(disk_used / disk_total * 100, 1) if disk_total else 0
            state["ssd"] = f"{disk_used}GB/{disk_total}GB {disk_perc}%"
        except:
            state["ssd"] = "N/D"
        state["ip"] = get_ip()
        state["time"] = datetime.now(ROME).strftime("%H:%M")
        time.sleep(30)

def update_display():
    while True:
        try:
            with canvas(device) as draw:
                draw.text((0, 0), "MQTT Server", fill="white")
                draw.text((90, 0), state["time"], fill="white")
                draw.text((0, 13), f"IP:{state['ip']}", fill="white")
                draw.text((0, 26), f"SSD:{state['ssd']}", fill="white")
                draw.text((0, 39), f"CPU:{state['temp']}", fill="white")
                if state["blink"]:
                    draw.ellipse([(120, 56), (127, 63)], fill="white")
        except Exception as e:
            print(f"Display error: {e}", flush=True)
        state["blink"] = not state["blink"]
        time.sleep(1)

print("Avvio OLED driver...", flush=True)

t_data = threading.Thread(target=update_data, daemon=True)
t_data.start()

update_display()
