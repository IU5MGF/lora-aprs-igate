import sqlite3
import os
import subprocess
from datetime import datetime
import pytz

DB_PATH = "/mnt/ssd/radio/data/aprs.db"
ROME = pytz.timezone("Europe/Rome")

def collect():
    # temperatura CPU
    try:
        temp_raw = open("/sys/class/thermal/thermal_zone0/temp").read().strip()
        cpu_temp = round(int(temp_raw) / 1000, 1)
    except:
        cpu_temp = None

    # RAM
    try:
        mem = {}
        for line in open("/proc/meminfo").readlines():
            parts = line.split()
            if parts[0] in ["MemTotal:", "MemAvailable:"]:
                mem[parts[0]] = int(parts[1])
        ram_total = mem.get("MemTotal:", 0) // 1024
        ram_avail = mem.get("MemAvailable:", 0) // 1024
        ram_used = ram_total - ram_avail
    except:
        ram_total = ram_used = None

    # SSD
    try:
        st = os.statvfs("/mnt/ssd")
        disk_total = st.f_blocks * st.f_frsize // (1024**3)
        disk_free = st.f_bavail * st.f_frsize // (1024**3)
        disk_used = disk_total - disk_free
    except:
        disk_total = disk_used = None

    # uptime
    try:
        uptime = int(float(open("/proc/uptime").read().split()[0]))
    except:
        uptime = None

    # CPU %
    try:
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'Cpu' in line or 'cpu' in line:
                import re
                m = re.search(r'(\d+\.?\d*)\s*id', line)
                if m:
                    cpu_perc = round(100 - float(m.group(1)), 1)
                    break
        else:
            cpu_perc = None
    except:
        cpu_perc = None

    # frequenza CPU MHz
    try:
        freq = int(open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read().strip()) // 1000
    except:
        freq = None

    # traffico rete
    try:
        net_stats = open("/proc/net/dev").read()
        for line in net_stats.split('\n'):
            if 'eth0' in line:
                parts = line.split()
                net_rx = int(parts[1])
                net_tx = int(parts[9])
                break
        else:
            net_rx = net_tx = None
    except:
        net_rx = net_tx = None

    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    
    db = sqlite3.connect(DB_PATH)
    
    # aggiungi colonne se non esistono
    for col in ['cpu_perc REAL', 'cpu_freq INTEGER', 'net_rx INTEGER', 'net_tx INTEGER']:
        try:
            db.execute(f"ALTER TABLE system_stats ADD COLUMN {col}")
            db.commit()
        except:
            pass
    
    db.execute("""INSERT INTO system_stats 
        (timestamp, cpu_temp, ram_used, ram_total, disk_used, disk_total, uptime_seconds, cpu_perc, cpu_freq, net_rx, net_tx)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, cpu_temp, ram_used, ram_total, disk_used, disk_total, uptime, cpu_perc, freq, net_rx, net_tx))
    db.commit()
    db.close()
    print(f"{ts} — temp:{cpu_temp}C cpu:{cpu_perc}% freq:{freq}MHz ram:{ram_used}/{ram_total}MB disk:{disk_used}/{disk_total}GB", flush=True)

collect()
