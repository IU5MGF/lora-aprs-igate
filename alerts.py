import sqlite3
import requests
import time
import pytz
import sys
import os
import subprocess
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

# Modalità di esecuzione: in Docker non esistono systemctl né "localhost:5000"
# (la dashboard è un altro container). IGATE_RUNTIME e DASHBOARD_URL arrivano
# dal docker-compose.yml; senza variabili vale l'installazione nativa (systemd).
IN_DOCKER     = os.environ.get("IGATE_RUNTIME") == "docker" or os.path.exists("/.dockerenv")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL",
                               "http://flask-dashboard:5000" if IN_DOCKER else "http://localhost:5000")

def load_alert_state():
    try:
        import json
        with open(ALERT_STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"silence": False, "igate_offline": False, "meshcom_offline": False, "containers": {}}

def save_alert_state():
    try:
        import json
        with open(ALERT_STATE_FILE, "w") as f:
            json.dump(alert_state, f)
    except Exception as e:
        print(f"Save alert state error: {e}", flush=True)

alert_state = load_alert_state()
# Assicura che alert_state.json sia scrivibile dall'utente corrente
try:
    import stat
    if os.path.exists(ALERT_STATE_FILE):
        os.chmod(ALERT_STATE_FILE, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
except Exception:
    pass

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

SERVICE_STALE_MINUTES = 30

SERVICE_DESCR = {
    "syslog-collector": "syslog-collector (nessun dato nel DB da oltre %d min)" % SERVICE_STALE_MINUTES,
    "mqtt-telegram": "mqtt-telegram (notifiche Telegram ferme)",
    "flask-dashboard": "flask-dashboard (dashboard non risponde)",
}

# Docker: systemctl non esiste nei container, la salute dei servizi si deduce da segnali
# osservabili (HTTP, dati nel DB). In caso di dubbio (DB bloccato ecc.) le sonde
# rispondono "attivo" per non generare falsi allarmi.
def probe_flask_dashboard():
    try:
        return requests.get(f"{DASHBOARD_URL}/api/live_temp", timeout=5).status_code == 200
    except Exception:
        return False

def probe_syslog_collector():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute("SELECT MAX(timestamp) FROM packets").fetchone()
        db.close()
        if not row or not row[0]:
            return True
        last_ts = datetime.strptime(row[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_ts).total_seconds() / 60 < SERVICE_STALE_MINUTES
    except Exception:
        return True

def probe_mqtt_telegram():
    try:
        with open(os.path.join(DATA_DIR, "last_notified_id"), "r") as f:
            last_id = int(f.read().strip())
    except Exception:
        return True
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%S")
        db = sqlite3.connect(DB_PATH)
        row = db.execute(
            """SELECT COUNT(*) FROM packets WHERE id > ? AND crc_ok=1 AND msg_type='RX'
               AND callsign IS NOT NULL AND callsign != ? AND (path IS NULL OR path != 'MESHCOM')
               AND timestamp < ?""",
            (last_id, CALLSIGN, cutoff)
        ).fetchone()
        db.close()
        return row[0] == 0
    except Exception:
        return True

SERVICE_PROBES = {
    "syslog-collector": probe_syslog_collector,
    "mqtt-telegram": probe_mqtt_telegram,
    "flask-dashboard": probe_flask_dashboard,
}

def check_containers():
    if not IN_DOCKER:
        check_services_systemd()
        return
    for name, probe in SERVICE_PROBES.items():
        running = probe()
        descr = SERVICE_DESCR[name]
        was_down = alert_state["containers"].get(name, False)
        if not running and not was_down:
            send_alert(
                f"\U0001f494 <b>ALERT \u2014 Servizio DOWN</b>\n"
                f"\u274c {descr}\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"ALERT: {name} down", flush=True)
            alert_state["containers"][name] = True
        elif running and was_down:
            send_alert(
                f"\u2705 <b>RIPRISTINO \u2014 Servizio UP</b>\n"
                f"\u2705 {name} tornato attivo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"RIPRISTINO: {name} up", flush=True)
            alert_state["containers"][name] = False
    save_alert_state()

# Installazione nativa: stato reale dei servizi da systemctl, con il riavvio
# automatico una tantum del server se syslog-collector resta giù per 3 cicli.
SYSTEMD_SERVICES = ["mosquitto", "syslog-collector", "mqtt-telegram", "flask-dashboard"]

def check_services_systemd():
    for name in SYSTEMD_SERVICES:
        try:
            result = subprocess.run(["systemctl", "is-active", name],
                                    capture_output=True, text=True)
            running = result.stdout.strip() == "active"
        except Exception:
            running = False
        was_down = alert_state["containers"].get(name, False)
        if not running and not was_down:
            send_alert(
                f"\U0001f494 <b>ALERT \u2014 Servizio DOWN</b>\n"
                f"\u274c {name} non attivo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"ALERT: {name} down", flush=True)
            alert_state["containers"][name] = True
        elif running and was_down:
            send_alert(
                f"\u2705 <b>RIPRISTINO \u2014 Servizio UP</b>\n"
                f"\u2705 {name} tornato attivo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            print(f"RIPRISTINO: {name} up", flush=True)
            alert_state["containers"][name] = False

        if name == "syslog-collector":
            if not running:
                count = alert_state.get("syslog_down_count", 0) + 1
                alert_state["syslog_down_count"] = count
                if count >= 3 and not alert_state.get("auto_reboot_done", False):
                    try:
                        alert_state["auto_reboot_done"] = True
                        save_alert_state()
                        send_alert(
                            f"\U0001f501 <b>Riavvio automatico avviato</b>\n"
                            f"syslog-collector giu da {count} minuti\n"
                            f"Se il problema persiste dopo il riavvio, serve controllo fisico\n"
                            f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                        )
                        print(f"AUTO-REBOOT: syslog-collector down da {count} cicli", flush=True)
                        subprocess.Popen(["sudo", "reboot"])
                    except Exception as e:
                        print(f"Auto-reboot error: {e}", flush=True)
            else:
                alert_state["syslog_down_count"] = 0
                alert_state["auto_reboot_done"] = False
    save_alert_state()

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
                    f"\U0001f504 <b>REBOOT AUTOMATICO iGate</b>\n"
                    f"Nessun pacchetto da <b>{int(minutes_ago)} minuti</b>\n"
                    f"Riavvio iGate in corso...\n"
                    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
                )
                log_event("REBOOT", f"Reboot iGate dopo {int(minutes_ago)} minuti di silenzio")
                alert_state["silence"] = False
                save_alert_state()
                reboot_igate()
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
            "SELECT MAX(timestamp) FROM packets WHERE callsign=? AND msg_type='TX'",
            (CALLSIGN,)
        ).fetchone()
        db.close()
        online = False
        if row and row[0]:
            last_dt = datetime.fromisoformat(row[0])
            minutes_since = (datetime.utcnow() - last_dt).total_seconds() / 60
            online = minutes_since <= 25
        if not online and not alert_state["igate_offline"]:
            send_alert(
                f"\U0001f4e1 <b>ALERT — iGate offline</b>\n"
                f"{CALLSIGN} — nessun beacon negli ultimi 25 minuti\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["igate_offline"] = True
            save_alert_state()
            log_event("IGATE_OFFLINE", f"{CALLSIGN} nessun beacon recente")
        elif online and alert_state["igate_offline"]:
            send_alert(
                f"\u2705 <b>RIPRISTINO — iGate online</b>\n"
                f"{CALLSIGN} beacon ricevuto di nuovo\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["igate_offline"] = False
            save_alert_state()
            log_event("IGATE_ONLINE", f"{CALLSIGN} ha ripreso a trasmettere")
    except Exception as e:
        print(f"iGate check error: {e}", flush=True)

def check_meshcom():
    try:
        import requests as _req
        from config import MESHCOM_IP, MESHCOM_CALLSIGN, HAS_MESHCOM
        if not HAS_MESHCOM:
            return
        try:
            r = _req.get(f"http://{MESHCOM_IP}/", timeout=5)
            online = r.status_code == 200
        except:
            online = False
        if not online and not alert_state.get("meshcom_offline", False):
            send_alert(
                f"\U0001f4e1 <b>ALERT — MeshCom offline</b>\n"
                f"{MESHCOM_CALLSIGN} non raggiungibile\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["meshcom_offline"] = True
            save_alert_state()
            log_event("MESHCOM_OFFLINE", f"{MESHCOM_CALLSIGN} non raggiungibile")
        elif online and alert_state.get("meshcom_offline", False):
            send_alert(
                f"\u2705 <b>RIPRISTINO — MeshCom online</b>\n"
                f"{MESHCOM_CALLSIGN} tornato raggiungibile\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["meshcom_offline"] = False
            save_alert_state()
            log_event("MESHCOM_ONLINE", f"{MESHCOM_CALLSIGN} tornato raggiungibile")
    except Exception as e:
        print(f"MeshCom check error: {e}", flush=True)
def check_temperature():
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/live_temp", timeout=5)
        temp = r.json().get("temp")
        if temp is None:
            return
        if temp >= 80 and not alert_state.get("temp_high", False):
            send_alert(
                f"\U0001f525 <b>ALERT \u2014 Temperatura CPU critica</b>\n"
                f"{CALLSIGN}: {temp}\u00b0C\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["temp_high"] = True
            save_alert_state()
            log_event("TEMP_HIGH", f"Temperatura critica: {temp}\u00b0C")
        elif temp < 75 and alert_state.get("temp_high", False):
            send_alert(
                f"\u2705 <b>RIPRISTINO \u2014 Temperatura normale</b>\n"
                f"{CALLSIGN}: {temp}\u00b0C\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["temp_high"] = False
            save_alert_state()
            log_event("TEMP_NORMAL", f"Temperatura tornata normale: {temp}\u00b0C")
    except Exception as e:
        print(f"Temperature check error: {e}", flush=True)

# Soglie batteria iGate (volt). Configurabili in config.py con BATTERY_LOW_V e
# BATTERY_OK_V; l'isteresi evita avvisi a raffica quando la tensione oscilla.
import config as _cfg
BATTERY_LOW_V        = getattr(_cfg, "BATTERY_LOW_V", 3.90)
BATTERY_OK_V         = getattr(_cfg, "BATTERY_OK_V", 4.00)
BATTERY_SAMPLES      = 3    # mediana delle ultime N letture, contro i valori spuri
BATTERY_MAX_AGE_MIN  = 120  # letture più vecchie vengono ignorate (c'è già l'avviso iGate offline)

def check_battery():
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute(
            """SELECT timestamp, voltage FROM packets
               WHERE callsign=? AND voltage IS NOT NULL AND voltage > 3 AND voltage < 5
               ORDER BY id DESC LIMIT ?""",
            (CALLSIGN, BATTERY_SAMPLES)
        ).fetchall()
        db.close()
        if len(rows) < BATTERY_SAMPLES:
            return
        last_ts = datetime.strptime(rows[0][0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last_ts).total_seconds() / 60 > BATTERY_MAX_AGE_MIN:
            return
        volt = sorted(r[1] for r in rows)[BATTERY_SAMPLES // 2]
        if volt < BATTERY_LOW_V and not alert_state.get("battery_low", False):
            send_alert(
                f"\U0001faab <b>ALERT \u2014 Batteria iGate bassa</b>\n"
                f"{CALLSIGN}: {volt:.2f} V (soglia {BATTERY_LOW_V:.2f} V)\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["battery_low"] = True
            save_alert_state()
            log_event("BATTERY_LOW", f"Batteria bassa: {volt:.2f} V")
        elif volt >= BATTERY_OK_V and alert_state.get("battery_low", False):
            send_alert(
                f"\u2705 <b>RIPRISTINO \u2014 Batteria iGate ok</b>\n"
                f"{CALLSIGN}: {volt:.2f} V\n"
                f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
            )
            alert_state["battery_low"] = False
            save_alert_state()
            log_event("BATTERY_OK", f"Batteria tornata a {volt:.2f} V")
    except Exception as e:
        print(f"Battery check error: {e}", flush=True)

print("Avvio alerts.py", flush=True)
log_event("AVVIO", "Sistema alert avviato")
send_alert(
    f"\U0001f514 <b>Sistema alert {CALLSIGN} attivo</b>\n"
    f"\u23f1 {datetime.now(ROME).strftime('%H:%M')}"
)

while True:
    check_containers()
    #check_silence()  # disabilitato
    check_igate()
    check_meshcom()
    check_temperature()
    check_battery()
    time.sleep(CHECK_INTERVAL)
