import re
import sqlite3
import requests
import time
import threading
import pytz
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import (
    CALLSIGN, BOT_TOKEN_NOTIFY, CHAT_ID_NOTIFY,
    BOT_TOKEN_ALERT, CHAT_ID_ALERT,
    DB_PATH, TIMEZONE, DATA_DIR
)

POLL_INTERVAL = 30
ROME = pytz.timezone(TIMEZONE)

def now_rome():
    return datetime.now(ROME)

def send_telegram(msg, alert=False):
    token = BOT_TOKEN_ALERT if alert else BOT_TOKEN_NOTIFY
    chat  = CHAT_ID_ALERT   if alert else CHAT_ID_NOTIFY
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
        if r.status_code != 200:
            print(f"Telegram error: {r.text}", flush=True)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

LAST_ID_FILE     = os.path.join(DATA_DIR, "last_notified_id")
REPORT_SENT_FILE = os.path.join(DATA_DIR, "last_report_sent")

def get_last_id():
    try:
        with open(LAST_ID_FILE, "r") as f:
            saved = int(f.read().strip())
            if saved > 0:
                print(f"Ripreso last_id dal file: {saved}", flush=True)
                return saved
    except:
        pass
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute("SELECT MAX(id) FROM packets").fetchone()
        db.close()
        return row[0] if row and row[0] else 0
    except:
        return 0

def save_last_id(pid):
    try:
        with open(LAST_ID_FILE, "w") as f:
            f.write(str(pid))
    except Exception as e:
        print(f"Save last_id error: {e}", flush=True)
def poll_packets():
    global last_id
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute(
            """SELECT id, timestamp, callsign, path, rssi, snr, distance, comment
               FROM packets WHERE id > ? AND crc_ok=1 AND msg_type='RX'
               AND callsign IS NOT NULL AND callsign != ?
               ORDER BY id ASC""",
            (last_id, CALLSIGN)
        ).fetchall()
        db.close()
        for row in rows:
            pid, ts, callsign, path, rssi, snr, distance, comment = row
            last_id = pid
            try:
                dt_utc = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                time_str = dt_utc.astimezone(ROME).strftime("%H:%M")
            except:
                time_str = ts[11:16] if ts else "-"
            rssi_str = f"{rssi} dBm" if rssi else "-"
            snr_str  = f"{snr} dB"   if snr  else "-"
            dist_str = f"{distance} km" if distance else "-"
            digipeated = " \u2605" if path and "*" in path else ""
            msg_text = (
                f"\U0001f534 LoRa APRS {CALLSIGN}\n"
                + f"\U0001f4e1 {callsign}{digipeated}\n"
                + f"\U0001f4f6 RSSI: <b>{rssi_str}</b>  SNR: <b>{snr_str}</b>\n"
                + f"\U0001f4cf Distanza: {dist_str}\n"
                + f"\U0001f500 Path: {path}\n"
                + (f"\U0001f4ac {comment}\n" if comment else "")
                + f"\u23f1 {time_str}"
            )
            try:
                db_check = sqlite3.connect(DB_PATH)
                count = db_check.execute(
                    "SELECT COUNT(*) FROM packets WHERE callsign=? AND id < ?",
                    (callsign, pid)
                ).fetchone()[0]
                db_check.close()
                if count == 0:
                    db_ev = sqlite3.connect(DB_PATH)
                    ts_ev = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                    db_ev.execute(
                        "INSERT INTO events (timestamp, type, message) VALUES (?,?,?)",
                        (ts_ev, "NUOVA_STAZIONE", f"Prima ricezione: {callsign} a {dist_str}")
                    )
                    db_ev.commit()
                    db_ev.close()
            except Exception as ev_e:
                print(f"Event log error: {ev_e}", flush=True)
            send_telegram(msg_text)
            print(f"Notifica inviata: {callsign}", flush=True)
            save_last_id(pid)
            time.sleep(1)
    except Exception as e:
        print(f"Poll error: {e}", flush=True)
def daily_report():
    now = now_rome()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    date_str  = (now - timedelta(days=1)).strftime("%d/%m/%Y")
    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM daily_stats WHERE date=?", (yesterday,)).fetchone()
        top5 = db.execute("""SELECT callsign, COUNT(*) as cnt FROM packets
            WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ?
            AND path NOT LIKE '%*%'
            AND replace(timestamp,'T',' ') >= datetime(?, '-2 hours')
            AND replace(timestamp,'T',' ') < datetime(?, '+22 hours')
            GROUP BY callsign ORDER BY cnt DESC LIMIT 5""",
            (CALLSIGN, yesterday, yesterday)).fetchall()
        db.close()
    except Exception as e:
        print(f"DB error daily: {e}", flush=True)
        return
    if not row:
        print(f"Nessun dato daily_stats per {yesterday}", flush=True)
        schedule_daily_report()
        return
    top5_lines = "".join(f"{i}. {r['callsign']} - {r['cnt']} pkt\n" for i, r in enumerate(top5, 1))
    best_str = f"{row['best_callsign']} - {row['best_distance']} km" if row['best_callsign'] else "-"
    peak_str = f"{row['peak_hour']}:00" if row['peak_hour'] else "-"
    msg = (
        f"\U0001f4ca <b>{CALLSIGN} - Report {date_str}</b>\n\n"
        + f"\U0001f4e6 Pacchetti totali: <b>{row['total_packets']}</b>\n"
        + f"\U0001f4f6 RF diretta: <b>{row['total_rf']}</b> | Digipeated: <b>{row['total_digi']}</b>\n"
        + f"\U0001f4e1 Stazioni uniche: <b>{row['unique_stations']}</b>\n"
        + f"\U0001f4cf Piu lontana RF: <b>{best_str}</b>\n"
        + f"\U0001f4ca RSSI medio: <b>{row['rssi_avg']} dBm</b>\n"
        + f"\U0001f550 Ora di punta: <b>{peak_str}</b>\n"
        + f"\u26a0 CRC errors: <b>{row['crc_errors']}</b>\n\n"
        + f"\U0001f51d <b>Top 5 RF diretta:</b>\n{top5_lines}"
    )
    send_telegram(msg)
    print(f"Report giornaliero inviato: {date_str}", flush=True)
    try:
        open(REPORT_SENT_FILE, "w").write(datetime.now(ROME).strftime("%Y-%m-%d"))
    except:
        pass
    schedule_daily_report()

def schedule_daily_report():
    now_rome_dt = datetime.now(ROME)
    next_8 = ROME.localize(
        now_rome_dt.replace(hour=8, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    )
    if now_rome_dt >= next_8:
        next_8 += timedelta(days=1)
    seconds = (next_8 - datetime.now(ROME)).total_seconds()
    print(f"Prossimo report giornaliero in {int(seconds)}s ({next_8.strftime('%Y-%m-%d %H:%M %Z')})", flush=True)
    timer = threading.Timer(seconds, daily_report)
    timer.daemon = True
    timer.start()
def system_report():
    try:
        try:
            temp_raw = open("/sys/class/thermal/thermal_zone0/temp").read().strip()
            temp = f"{int(temp_raw)/1000:.1f}C"
        except:
            temp = "N/D"
        mem = {}
        for line in open("/proc/meminfo").readlines():
            parts = line.split()
            if parts[0] in ["MemTotal:", "MemAvailable:"]:
                mem[parts[0]] = int(parts[1])
        ram_total = mem.get("MemTotal:", 0) // 1024
        ram_avail = mem.get("MemAvailable:", 0) // 1024
        ram_used  = ram_total - ram_avail
        ram_perc  = round(ram_used / ram_total * 100, 1) if ram_total else 0
        try:
            from config import HAS_SSD, SSD_MOUNT
            if not HAS_SSD: raise Exception("no ssd")
            st = os.statvfs(SSD_MOUNT)
            disk_total   = st.f_blocks * st.f_frsize // (1024**3)
            disk_free    = st.f_bavail * st.f_frsize // (1024**3)
            disk_used_gb = disk_total - disk_free
            disk_perc    = round(disk_used_gb / disk_total * 100, 1) if disk_total else 0
            disk_str     = f"{disk_used_gb}GB / {disk_total}GB ({disk_perc}%)"
        except:
            disk_str = "N/D"
        try:
            secs   = float(open("/proc/uptime").read().split()[0])
            h      = int(secs // 3600)
            m      = int((secs % 3600) // 60)
            uptime = f"{h}h {m}m"
        except:
            uptime = "N/D"
        now = now_rome().strftime("%H:%M")
        msg = (
            "\U0001f5a5 <b>Report sistema RPi</b>\n"
            + f"\u23f1 {now}\n\n"
            + f"\U0001f321 Temperatura: <b>{temp}</b>\n"
            + f"\U0001f4be RAM: <b>{ram_used}MB / {ram_total}MB ({ram_perc}%)</b>\n"
            + f"\U0001f4bd SSD: <b>{disk_str}</b>\n"
            + f"\u26a1 Uptime: <b>{uptime}</b>"
        )
        send_telegram(msg, alert=True)
        print(f"Report sistema inviato: {now}", flush=True)
    except Exception as e:
        print(f"System report error: {e}", flush=True)
    timer = threading.Timer(7200, system_report)
    timer.daemon = True
    timer.start()

def start_system_report():
    print("Avvio report sistema ogni 2 ore", flush=True)
    system_report()

def check_missed_report():
    now = datetime.now(ROME)
    today_str = now.strftime("%Y-%m-%d")
    if now.hour >= 8:
        try:
            with open(REPORT_SENT_FILE, "r") as f:
                last_sent = f.read().strip()
            if last_sent == today_str:
                print(f"Report già inviato oggi ({today_str}), skip", flush=True)
                return
        except:
            pass
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            db  = sqlite3.connect(DB_PATH)
            row = db.execute("SELECT date FROM daily_stats WHERE date=?", (yesterday,)).fetchone()
            db.close()
            if row:
                print("Controllo report mancato: invio report di ieri", flush=True)
                daily_report()
            else:
                print(f"Nessun dato daily_stats per {yesterday}, skip", flush=True)
        except Exception as e:
            print(f"Check missed report error: {e}", flush=True)

last_id = get_last_id()
print(f"Ultimo ID nel DB: {last_id}", flush=True)

send_telegram(
    f"\u2705 <b>{CALLSIGN} sistema avviato</b>\n"
    + "\U0001f5a5 RPi online\n"
    + f"\u23f1 {now_rome().strftime('%H:%M')}",
    alert=True
)

check_missed_report()
schedule_daily_report()
start_system_report()

while True:
    poll_packets()
    time.sleep(POLL_INTERVAL)
