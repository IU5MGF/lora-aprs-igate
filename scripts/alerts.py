import sqlite3
import requests
import time
import subprocess
import pytz
from datetime import datetime, timezone, timedelta

ALERT_TOKEN = "ALERT_TOKEN_PLACEHOLDER"
CHAT_ID = "CHAT_ID_PLACEHOLDER"
DB_PATH = "/mnt/ssd/radio/data/aprs.db"
ROME = pytz.timezone("Europe/Rome")

SILENCE_MINUTES = 60
REBOOT_MINUTES = 120
IGATE_OFFLINE_MINUTES = 30
BATTERY_THRESHOLD = 20.0
CHECK_INTERVAL = 60

ALERT_STATE_FILE = "/mnt/ssd/radio/data/alert_state.json"

def load_alert_state():
    try:
        import json
        with open(ALERT_STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"silence": False, "igate_offline": False, "battery_low": False, "containers": {}}

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
        import sqlite3 as _sq
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        db = _sq.connect(DB_PATH)
        db.execute("INSERT INTO events (timestamp, type, message) VALUES (?,?,?)", (ts, event_type, message))
        db.commit()
        db.close()
        print(f"EVENT: {event_type} — {message}", flush=True)
    except Exception as e:
        print(f"Log event error: {e}", flush=True)

def send_alert(msg):
    url = f"https://api.telegram.org/bot{ALERT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
        if r.status_code != 200:
            print(f"Alert error: {r.text}", flush=True)
    except Exception as e:
        print(f"Alert error: {e}", flush=True)

def reboot_igate():
    try:
        requests.get("http://IGATE_IP_PLACEHOLDER/action?type=reboot", timeout=5)
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
            result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
            running = result.stdout.strip() == "active"
        except:
            running = False
        was_down = alert_state["containers"].get(name, False)
        if not running and not was_down:
            send_alert(f"💔 <b>ALERT — Servizio DOWN</b>\n❌ {name} non attivo\n⏱ {datetime.now(ROME).strftime('%H:%M')}")
            print(f"ALERT: {name} down", flush=True)
            alert_state["containers"][name] = True
        elif running and was_down:
            send_alert(f"✅ <b>RIPRISTINO — Servizio UP</b>\n✅ {name} tornato attivo\n⏱ {datetime.now(ROME).strftime('%H:%M')}")
            print(f"RIPRISTINO: {name} up", flush=True)
            alert_state["containers"][name] = False

def check_silence():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            """SELECT MAX(timestamp) FROM packets
               WHERE crc_ok=1 AND msg_type='RX'
               AND callsign IS NOT NULL
               AND callsign != 'CALLSIGN_PLACEHOLDER'"""
        ).fetchone()
        db.close()

        if row and row[0]:
            last_ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60

            if minutes_ago >= REBOOT_MINUTES and alert_state["silence"]:
                send_alert(
                    f"🔄 <b>REBOOT AUTOMATICO</b>\n"
                    f"Nessun pacchetto da <b>{int(minutes_ago)} minuti</b>\n"
                    f"Riavvio iGate e server in corso...\n"
                    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                )
                print(f"REBOOT: silenzio da {int(minutes_ago)} min", flush=True)
                log_event("REBOOT", f"Reboot automatico dopo {int(minutes_ago)} minuti di silenzio")
                reboot_igate()
                time.sleep(5)
                reboot_rpi()
            elif minutes_ago >= SILENCE_MINUTES and not alert_state["silence"]:
                send_alert(
                    f"🔇 <b>ALERT — Silenzio radio</b>\n"
                    f"Nessun pacchetto RF ricevuto da <b>{int(minutes_ago)} minuti</b>\n"
                    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                )
                print(f"ALERT: silenzio radio da {int(minutes_ago)} min", flush=True)
                alert_state["silence"] = True
                save_alert_state()
                log_event("SILENZIO", f"Nessun pacchetto RF da {int(minutes_ago)} minuti")
            elif minutes_ago < SILENCE_MINUTES and alert_state["silence"]:
                send_alert(
                    f"📡 <b>RIPRISTINO — Ricezione RF ripresa</b>\n"
                    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                )
                print("RIPRISTINO: ricezione RF ripresa", flush=True)
                alert_state["silence"] = False
                save_alert_state()
                log_event("RIPRISTINO_RF", "Ricezione RF ripresa")
    except Exception as e:
        print(f"Silence check error: {e}", flush=True)

def check_igate():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            """SELECT MAX(timestamp) FROM packets
               WHERE callsign='CALLSIGN_PLACEHOLDER'"""
        ).fetchone()
        db.close()

        if row and row[0]:
            last_ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60

            if minutes_ago >= IGATE_OFFLINE_MINUTES and not alert_state["igate_offline"]:
                send_alert(
                    f"📡 <b>ALERT — iGate offline</b>\n"
                    f"CALLSIGN_PLACEHOLDER non trasmette da <b>{int(minutes_ago)} minuti</b>\n"
                    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                )
                print(f"ALERT: iGate offline da {int(minutes_ago)} min", flush=True)
                alert_state["igate_offline"] = True
                save_alert_state()
                log_event("IGATE_OFFLINE", f"CALLSIGN_PLACEHOLDER non trasmette da {int(minutes_ago)} minuti")
            elif minutes_ago < IGATE_OFFLINE_MINUTES and alert_state["igate_offline"]:
                send_alert(
                    f"✅ <b>RIPRISTINO — iGate online</b>\n"
                    f"CALLSIGN_PLACEHOLDER ha ripreso a trasmettere\n"
                    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                )
                print("RIPRISTINO: iGate online", flush=True)
                alert_state["igate_offline"] = False
                save_alert_state()
                log_event("IGATE_ONLINE", "CALLSIGN_PLACEHOLDER ha ripreso a trasmettere")
    except Exception as e:
        print(f"iGate check error: {e}", flush=True)

def check_battery():
    try:
        import re
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            """SELECT comment FROM packets
               WHERE callsign='IU5MGF-13' AND comment IS NOT NULL
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        db.close()

        if row and row[0]:
            bat_match = re.search(r'Bat[t]?=?([\d.]+)V.*?\((\d+)%\)', row[0])
            if bat_match:
                percent = float(bat_match.group(2))
                if percent <= BATTERY_THRESHOLD and not alert_state["battery_low"]:
                    send_alert(
                        f"🔋 <b>ALERT — Batteria bassa IU5MGF-13</b>\n"
                        f"Batteria al <b>{percent}%</b>\n"
                        f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
                    )
                    print(f"ALERT: batteria bassa {percent}%", flush=True)
                    alert_state["battery_low"] = True
                    log_event("BATTERIA_BASSA", f"IU5MGF-13 batteria al {percent}%")
                elif percent > BATTERY_THRESHOLD and alert_state["battery_low"]:
                    alert_state["battery_low"] = False
    except Exception as e:
        print(f"Battery check error: {e}", flush=True)

print("Avvio alerts.py", flush=True)
log_event("AVVIO", "Sistema alert avviato")
send_alert(
    f"🔔 <b>Sistema alert CALLSIGN_PLACEHOLDER attivo</b>\n"
    f"⏱ {datetime.now(ROME).strftime('%H:%M')}"
)

while True:
    check_containers()
    check_silence()
    check_igate()
    check_battery()
    time.sleep(CHECK_INTERVAL)
