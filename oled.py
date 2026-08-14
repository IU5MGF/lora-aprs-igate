import time
import os
import socket
import threading
import signal
import sys
import pytz
from datetime import datetime

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import CALLSIGN, TIMEZONE, HAS_OLED, OLED_I2C_ADDR, HAS_SSD, SSD_MOUNT

if not HAS_OLED:
    print("OLED non configurato (HAS_OLED=False), uscita.", flush=True)
    sys.exit(0)

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

ROME = pytz.timezone(TIMEZONE)
serial = i2c(port=1, address=OLED_I2C_ADDR)
device = ssd1306(serial)

with canvas(device) as draw:
    draw.text((10, 10), CALLSIGN, fill="white")
    draw.text((5, 25), "Server RPi", fill="white")
    draw.text((15, 40), "Avvio...", fill="white")
time.sleep(3)

state = {"uptime": "N/D", "ssd": "N/D", "ip": "N/D", "time": "--:--", "blink": False}

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
            secs = float(open("/proc/uptime").read().split()[0])
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            state["uptime"] = f"{h}h{m}m"
        except:
            state["uptime"] = "N/D"
        if HAS_SSD:
            try:
                st = os.statvfs(SSD_MOUNT)
                disk_total = st.f_blocks * st.f_frsize // (1024**3)
                disk_free  = st.f_bavail * st.f_frsize // (1024**3)
                disk_used  = disk_total - disk_free
                disk_perc  = round(disk_used / disk_total * 100, 1) if disk_total else 0
                state["ssd"] = f"{disk_used}GB/{disk_total}GB {disk_perc}%"
            except:
                state["ssd"] = "N/D"
        else:
            state["ssd"] = "no SSD"
        state["ip"]   = get_ip()
        state["time"] = datetime.now(ROME).strftime("%H:%M")
        time.sleep(30)

def update_display():
    while True:
        try:
            with canvas(device) as draw:
                draw.text((0,  0), "MQTT Server",          fill="white")
                draw.text((90, 0), state["time"],           fill="white")
                draw.text((0, 13), f"IP:{state['ip']}",    fill="white")
                draw.text((0, 26), f"SSD:{state['ssd']}",  fill="white")
                draw.text((0, 39), f"UP:{state['uptime']}", fill="white")
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
