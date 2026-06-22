#!/usr/bin/env python3
import sys, json, socket, sqlite3, logging, re, requests
from datetime import datetime, timezone

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, MESHCOM_CALLSIGN, BOT_TOKEN_NOTIFY, CHAT_ID_NOTIFY, BOT_TOKEN_ALERT, CHAT_ID_ALERT, CALLSIGN, TIMEZONE

import pytz
ROME = pytz.timezone(TIMEZONE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [meshcom-udp] %(message)s")
log = logging.getLogger()

UDP_PORT = 1799

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def send_notify(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN_NOTIFY}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID_NOTIFY, "text": msg}, timeout=5)
    except Exception as e:
        log.warning(f"notify error: {e}")

def handle_pos(d, db):
    src = d.get("src", "")
    callsign = src.split(",")[0]
    lat = d.get("lat")
    lon = d.get("long")
    lat_dir = d.get("lat_dir", "N")
    lon_dir = d.get("long_dir", "E")
    if lat is None or lon is None:
        return
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return
    if lat_dir == "S": lat_f = -lat_f
    if lon_dir == "W": lon_f = -lon_f
    if lat_f == 0.0 and lon_f == 0.0:
        return

    alt  = d.get("alt")
    batt = d.get("batt")
    rssi = d.get("rssi")
    snr  = d.get("snr")
    comment_parts = []
    if batt is not None: comment_parts.append(f"B={batt}")
    if alt is not None:  comment_parts.append(f"A={alt}")
    comment = " ".join(comment_parts) if comment_parts else None

    ts = now_utc()
    try:
        db.execute("""INSERT OR IGNORE INTO packets
            (timestamp, callsign, path, lat, lon, comment, msg_type, crc_ok, rssi, snr)
            VALUES (?,?,?,?,?,?,?,1,?,?)""",
            (ts, callsign, "MESHCOM", lat_f, lon_f, comment, "RX", rssi, snr))
        db.commit()
        log.info(f"POS: {callsign} lat={lat_f} lon={lon_f} batt={batt} alt={alt}")
    except Exception as e:
        log.warning(f"handle_pos db error: {e}")

def handle_msg(d, db):
    src  = d.get("src", "")
    dst  = d.get("dst", "*")
    text = d.get("msg", "")
    src_type = d.get("src_type", "")
    callsign = src.split(",")[0]

    if re.match(r'^\{CET\}\d{4}-\d{2}-\d{2}', text):
        return
    if callsign == MESHCOM_CALLSIGN and src_type == "node":
        return

    ts = now_utc()
    try:
        cur = db.execute(
            "INSERT OR IGNORE INTO meshcom_messages (timestamp, callsign, dest, message) VALUES (?,?,?,?)",
            (ts, callsign, dst, text)
        )
        db.commit()
        if cur.rowcount > 0:
            log.info(f"MSG: {callsign} -> {dst}: {text[:50]}")
            notify_message(callsign, dst, text)
    except Exception as e:
        log.warning(f"handle_msg db error: {e}")

def notify_message(callsign, dst, text):
    time_str = datetime.now(ROME).strftime("%H:%M")
    dest_str = f" -> {dst}" if dst and dst not in ("*", "222") else " -> ALL"
    # Controlla se il messaggio è diretto al nostro nodo
    is_direct = dst and (MESHCOM_CALLSIGN in dst or CALLSIGN in dst)
    if is_direct:
        msg = (
            "\U0001f514 <b>MESSAGGIO DIRETTO MeshCom</b>\n"
            + f"\U0001f4e1 Da: <b>{callsign}</b> -> <b>{dst}</b>\n"
            + f"\U0001f4dd {text}\n"
            + f"\u23f1 {time_str}"
        )
        send_notify(msg)
        # Invia anche su bot alert per maggiore visibilità
        try:
            import requests as _req
            _req.post(f"https://api.telegram.org/bot{BOT_TOKEN_ALERT}/sendMessage",
                data={"chat_id": CHAT_ID_ALERT, "text": msg.replace("<b>","").replace("</b>",""), "parse_mode": "HTML"},
                timeout=5)
        except Exception as e:
            log.warning(f"alert notify error: {e}")
    else:
        msg = (
            "\U0001f4e1 MeshCom " + MESHCOM_CALLSIGN + "\n"
            + f"\U0001f4ac {callsign}{dest_str}\n"
            + f"\U0001f4dd {text}\n"
            + f"\u23f1 {time_str}"
        )
        send_notify(msg)

def handle_tele(d, db):
    src = d.get("src", "")
    callsign = src.split(",")[0]
    log.info(f"TELE: {callsign} -> {d}")

    temp = d.get("temp1")
    hum  = d.get("hum")
    qfe  = d.get("qfe")
    qnh  = d.get("qnh")
    gas  = d.get("gas")

    if temp and temp != 0:
        ts = now_utc()
        try:
            db.execute(
                "INSERT INTO meshcom_weather (timestamp, callsign, temp, hum, qfe, qnh, gas) VALUES (?,?,?,?,?,?,?)",
                (ts, callsign, temp, hum, qfe, qnh, gas)
            )
            db.commit()
            log.info(f"WX: {callsign} temp={temp} hum={hum} qnh={qnh} gas={gas}")
            send_notify(
                f"WX {callsign}\n"
                f"Temp: {temp} C\n"
                f"Umidita: {hum} %\n"
                f"QFE: {qfe} hPa\n"
                f"QNH: {qnh} hPa\n"
                f"Gas: {gas} ohm"
            )
        except Exception as e:
            log.warning(f"handle_tele db error: {e}")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    log.info(f"meshcom-udp-listener avviato su porta {UDP_PORT}")
    db = get_db()
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            text = data.decode("utf-8", errors="ignore")
            d = json.loads(text)
            mtype = d.get("type")
            if mtype == "pos":
                handle_pos(d, db)
            elif mtype == "msg":
                handle_msg(d, db)
            elif mtype == "tele":
                handle_tele(d, db)
        except json.JSONDecodeError:
            log.warning(f"JSON non valido: {text[:100]}")
        except Exception as e:
            log.error(f"Errore: {e}")
            try:
                db.close()
            except: pass
            db = get_db()

if __name__ == "__main__":
    main()
