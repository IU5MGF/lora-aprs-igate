import sqlite3
import os
import sys
import subprocess
import re
from datetime import datetime
import pytz

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, TIMEZONE, HAS_SSD, SSD_MOUNT

ROME = pytz.timezone(TIMEZONE)

def ensure_schema():
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute("ALTER TABLE system_stats ADD COLUMN disk_label TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        db.close()
ensure_schema()

def collect():
    try:
        temp_raw = open("/sys/class/thermal/thermal_zone0/temp").read().strip()
        cpu_temp = round(int(temp_raw) / 1000, 1)
    except:
        cpu_temp = None
    try:
        mem = {}
        for line in open("/proc/meminfo").readlines():
            parts = line.split()
            if parts[0] in ["MemTotal:", "MemAvailable:"]:
                mem[parts[0]] = int(parts[1])
        ram_total = mem.get("MemTotal:", 0) // 1024
        ram_avail = mem.get("MemAvailable:", 0) // 1024
        ram_used  = ram_total - ram_avail
    except:
        ram_total = ram_used = None
    disk_total = disk_used = None
    disk_label = "SSD" if HAS_SSD else "SD Card"
    try:
        disk_path = SSD_MOUNT if HAS_SSD else "/"
        st = os.statvfs(disk_path)
        disk_total = st.f_blocks * st.f_frsize // (1024**3)
        disk_free  = st.f_bavail * st.f_frsize // (1024**3)
        disk_used  = disk_total - disk_free
    except:
        pass
    try:
        uptime = int(float(open("/proc/uptime").read().split()[0]))
    except:
        uptime = None
    cpu_perc = None
    try:
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'Cpu' in line or 'cpu' in line:
                m = re.search(r'(\d+\.?\d*)\s*id', line)
                if m:
                    cpu_perc = round(100 - float(m.group(1)), 1)
                    break
    except:
        pass
    try:
        freq = int(open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read().strip()) // 1000
    except:
        freq = None
    net_rx = net_tx = None
    try:
        for line in open("/proc/net/dev").readlines():
            if 'eth0' in line:
                parts = line.split()
                net_rx = int(parts[1])
                net_tx = int(parts[9])
                break
    except:
        pass
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    db = sqlite3.connect(DB_PATH)
    for col in ['cpu_perc REAL', 'cpu_freq INTEGER', 'net_rx INTEGER', 'net_tx INTEGER']:
        try:
            db.execute(f"ALTER TABLE system_stats ADD COLUMN {col}")
            db.commit()
        except:
            pass
    db.execute("""INSERT INTO system_stats
        (timestamp, cpu_temp, ram_used, ram_total, disk_used, disk_total,
         uptime_seconds, cpu_perc, cpu_freq, net_rx, net_tx, disk_label)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, cpu_temp, ram_used, ram_total, disk_used, disk_total,
         uptime, cpu_perc, freq, net_rx, net_tx, disk_label))
    db.commit()
    db.close()
    print(f"{ts} — temp:{cpu_temp}C cpu:{cpu_perc}% ram:{ram_used}/{ram_total}MB disk:{disk_used}/{disk_total}GB", flush=True)

collect()
