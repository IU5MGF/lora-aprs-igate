import sqlite3
import requests
import time
import subprocess
import pytz
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import (
    CALLSIGN, BOT_TOKEN_ALERT, CHAT_ID_ALERT,
    IGATE_IP, DB_PATH, TIMEZONE, DATA_DIR
)

ROME = pytz.timezone(TIMEZONE)

SILENCE_MINUTES       = 60
REBOOT_MINUTES        = 120
IGATE_OFFLINE_MINUTES = 30
CHECK_INTERVAL        = 60

ALERT_STATE_FILE = os.path.join(DATA_DIR, "alert_state.json")

def load_alert_state():
    try:
        import json
        with open(ALERT_STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"silence": False, "igate_offline": False, "containers": {}}

def save_alert_state():
    try:
        import json
        with open(ALERT_STATE_FILE, "w") as f:
            json.dump(alert_state, f)
    except Exception as e:
        print(f"Save alert state error: {e}", flush=True)

alert_state = load_alert_state()

def log_event(event_type, message):
    try:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        db = sqlite3.connect(DB_PATH)
        db.execute("INSERT INTO events (timestamp, type, message) VALUES (?,?,?)",
                   (ts, event_type, message))
        db.commit()
        db.close()
        print(f"EVENT: {event_type} — {message}", flush=True)
    except Exception as e:
        print(f"Log event error: {e}", flush=True)

def send_alert(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN_ALERT}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID_ALERT, "text": msg, "parse_mode": "HTML"})
        if r.status_code != 200:
            print(f"Alert error: {r.text}", flush=True)
    except Exception as e:
        print(f"Alert error: {e}", flush=True)

def reboot_igate():
    try:
        requests.get(f"http://{IGATE_IP}/action?type=reboot", timeout=5)
        print("Reboot iGate inviato", flush=True)
    except Exception as e:
        print(f"Reboot iGate error: {e}", flush=True)

def reboot_rpi():
    print("Reboot RPi in corso...", flush=True)
    subprocess.Popen(["sudo", "reboot"])
def check_containers():
    services = ["mosquitto", "syslog-collector", "mqtt-telegram", "flask-dashboard"]
    for name in services:
        try:
            result = subprocess.run(["systemctl", "is-active", name],
                                    capture_output=True, text=True)
            running = result.stdout.strip() == "active"
        except:
            running = False
        was_down = alert_state["containers"].get(name, False)
        if not running and not was_down:
            send_alert(
                f"\U0001f494 <b>ALERT — Servizio DOWN</b>\n"
                f"\u274c {name} non attivo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"ALERT: {name} down", flush=True)
            alert_state["containers"][name] = True
        elif running and was_down:
            send_alert(
                f"\u2705 <b>RIPRISTINO — Servizio UP</b>\n"
                f"\u2705 {name} tornato attivo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"RIPRISTINO: {name} up", flush=True)
            alert_state["containers"][name] = False

def check_silence():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            """SELECT MAX(timestamp) FROM packets
               WHERE crc_ok=1 AND msg_type='RX'
               AND callsign IS NOT NULL AND callsign != ?""",
            (CALLSIGN,)
        ).fetchone()
        db.close()
        if row and row[0]:
            last_ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
            if minutes_ago >= REBOOT_MINUTES and alert_state["silence"]:
                send_alert(
                    f"\U0001f504 <b>REBOOT AUTOMATICO</b>\n"
                    f"Nessun pacchetto da <b>{int(minutes_ago)} minuti</b>\n"
                    f"Riavvio iGate e server in corso...\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                log_event("REBOOT", f"Reboot automatico dopo {int(minutes_ago)} minuti di silenzio")
                reboot_igate()
                time.sleep(5)
                reboot_rpi()
            elif minutes_ago >= SILENCE_MINUTES and not alert_state["silence"]:
                send_alert(
                    f"\U0001f507 <b>ALERT — Silenzio radio</b>\n"
                    f"Nessun pacchetto RF ricevuto da <b>{int(minutes_ago)} minuti</b>\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                alert_state["silence"] = True
                save_alert_state()
                log_event("SILENZIO", f"Nessun pacchetto RF da {int(minutes_ago)} minuti")
            elif minutes_ago < SILENCE_MINUTES and alert_state["silence"]:
                send_alert(
                    f"\U0001f4e1 <b>RIPRISTINO — Ricezione RF ripresa</b>\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                alert_state["silence"] = False
                save_alert_state()
                log_event("RIPRISTINO_RF", "Ricezione RF ripresa")
    except Exception as e:
        print(f"Silence check error: {e}", flush=True)
def check_igate():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            "SELECT MAX(timestamp) FROM packets WHERE callsign=?",
            (CALLSIGN,)
        ).fetchone()
        db.close()
        if row and row[0]:
            last_ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
            if minutes_ago >= IGATE_OFFLINE_MINUTES and not alert_state["igate_offline"]:
                send_alert(
                    f"\U0001f4e1 <b>ALERT — iGate offline</b>\n"
                    f"{CALLSIGN} non trasmette da <b>{int(minutes_ago)} minuti</b>\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                alert_state["igate_offline"] = True
                save_alert_state()
                log_event("IGATE_OFFLINE", f"{CALLSIGN} non trasmette da {int(minutes_ago)} minuti")
            elif minutes_ago < IGATE_OFFLINE_MINUTES and alert_state["igate_offline"]:
                send_alert(
                    f"\u2705 <b>RIPRISTINO — iGate online</b>\n"
                    f"{CALLSIGN} ha ripreso a trasmettere\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                alert_state["igate_offline"] = False
                save_alert_state()
                log_event("IGATE_ONLINE", f"{CALLSIGN} ha ripreso a trasmettere")
    except Exception as e:
        print(f"iGate check error: {e}", flush=True)

print("Avvio alerts.py", flush=True)
log_event("AVVIO", "Sistema alert avviato")
send_alert(
    f"\U0001f514 <b>Sistema alert {CALLSIGN} attivo</b>\n"
    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
)

while True:
    check_containers()
    check_silence()
    check_igate()
    time.sleep(CHECK_INTERVAL)
