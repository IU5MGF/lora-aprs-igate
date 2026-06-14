#!/usr/bin/env python3
import sys, time, re, sqlite3, logging, requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, MESHCOM_IP, MESHCOM_CALLSIGN, BOT_TOKEN_NOTIFY, CHAT_ID_NOTIFY, TIMEZONE

import pytz
ROME = pytz.timezone(TIMEZONE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [meshcom-poller] %(message)s")
log = logging.getLogger()

BASE    = f"http://{MESHCOM_IP}"
TIMEOUT = 5

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def local_to_utc(ts_str):
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        return (dt - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    except:
        return now_utc()

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def fetch(path):
    try:
        r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
        return r.text
    except Exception as e:
        log.warning(f"fetch {path} failed: {e}")
        return None

def send_notify(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN_NOTIFY}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID_NOTIFY, "text": msg}, timeout=5)
    except Exception as e:
        log.warning(f"notify error: {e}")

def parse_info(html):
    def val(label):
        m = re.search(rf'<td>{re.escape(label)}</td><td>(.*?)</td>', html, re.DOTALL)
        return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else None
    batt_v, batt_pct = None, None
    batt_raw = val("Battery")
    if batt_raw:
        m = re.search(r'([\d.]+)V\s*\((\d+)%\)', batt_raw)
        if m:
            batt_v, batt_pct = float(m.group(1)), int(m.group(2))
    wifi_rssi = None
    try: wifi_rssi = int(val("WiFi RSSI"))
    except: pass
    gw = val("Settings")
    return {
        "callsign": MESHCOM_CALLSIGN, "firmware": val("Firmware"),
        "battery_v": batt_v, "battery_pct": batt_pct,
        "wifi_rssi": wifi_rssi,
        "gateway_on": 1 if gw and "Gateway: on" in gw else 0,
        "uptime_start": val("Start Date"),
    }

def parse_mheard(html):
    nodes = []
    for card in re.finditer(r'<label class="cardlabel">(.*?)</div></div>', html, re.DOTALL):
        block = card.group(0)
        call_m = re.search(r'\?call=([\w-]+)"', block)
        ts_m   = re.search(r'\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\)', block)
        def fld(label):
            m = re.search(rf'<span class="font-bold">{label}:</span><br><span>(.*?)</span>', block)
            return m.group(1).strip() if m else None
        if not call_m:
            continue
        def to_float(s):
            try: return float(re.sub(r'[^\d.\-]', '', s)) if s else None
            except: return None
        def to_int(s):
            try: return int(re.sub(r'[^\d\-]', '', s)) if s else None
            except: return None
        lat_s, lon_s = fld("Lat") or "", fld("Lon") or ""
        lat, lon = None, None
        lm = re.match(r'([NS])([\d.]+)', lat_s)
        if lm:
            v = float(lm.group(2))
            lat = v * (-1 if lm.group(1)=='S' else 1) if v != 0.0 else None
        lm = re.match(r'([EW])([\d.]+)', lon_s)
        if lm:
            v = float(lm.group(2))
            lon = v * (-1 if lm.group(1)=='W' else 1) if v != 0.0 else None
        ts = ts_m.group(1).replace(" ", "T") if ts_m else now_utc()
        nodes.append({
            "timestamp": local_to_utc(ts),
            "callsign": call_m.group(1),
            "rssi": to_int(fld("RSSI")), "snr": to_int(fld("SNR")),
            "distance": to_float(fld("Dist")),
            "lat": lat, "lon": lon, "alt": to_int(fld("Alt")),
            "hardware": fld("Hardware"), "msg_type": fld("Type"),
        })
    return nodes

def parse_rxlog(html):
    entries = []
    for m in re.finditer(
        r'<\d+>([\d:]+)\s+:\w+\s+\d+\s+\w+\s+\S+\s+LH:\w+\s+([\w,\-]+)>([\w*]+)\s*(.*?)</nobr>',
        html, re.DOTALL
    ):
        time_str = m.group(1)
        path_str = m.group(2)
        dst      = m.group(3)
        payload  = m.group(4).strip()
        rssi, snr = None, None
        rs_m = re.search(r'@R\d+;(\d+),(\d+),(\d+);', payload)
        if rs_m:
            rssi = -int(rs_m.group(2))
            snr  =  int(rs_m.group(3))
        today_local = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        try:
            dt_local = datetime.strptime(f"{today_local}T{time_str}", "%Y-%m-%dT%H:%M:%S")
            dt_utc   = dt_local - timedelta(hours=2)
            today    = dt_utc.strftime("%Y-%m-%d")
            time_utc = dt_utc.strftime("%H:%M:%S")
        except:
            today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            time_utc = time_str
        lat, lon, alt, comment = None, None, None, None
        if dst == '*':
            pos_m = re.search(r'!(\d{2})(\d{2}\.\d+)([NS])[/\\](\d{3})(\d{2}\.\d+)([EW])', payload)
            if pos_m:
                lat = float(pos_m.group(1)) + float(pos_m.group(2))/60
                if pos_m.group(3) == 'S': lat = -lat
                lon = float(pos_m.group(4)) + float(pos_m.group(5))/60
                if pos_m.group(6) == 'W': lon = -lon
            alt_m = re.search(r'/A=(\d+)', payload)
            if alt_m: alt = int(int(alt_m.group(1)) * 0.3048)
            comment = payload
        entries.append({
            "timestamp": f"{today}T{time_utc}",
            "raw":       f"{path_str}>{dst} {payload}"[:250],
            "src_call":  path_str.split(",")[0],
            "dst_call":  dst, "path": path_str,
            "msg_type":  dst[:2] if dst else None,
            "rssi": rssi, "snr": snr,
            "lat": lat, "lon": lon, "alt": alt, "comment": comment,
        })
    return entries

def parse_messages(html):
    messages = []
    # pattern: >CALLSIGN,GW</a>>DEST</p><p...>TIMESTAMP</p><p...>TEXT</p>
    for m in re.finditer(
        r'href="https://aprs\.fi/\?call=[\w,\-]+">([\w,\-]+)</a>>(\S*)</p>'
        r'<p[^>]*>(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})</p>'
        r'<p[^>]*>(.*?)</p>',
        html, re.DOTALL
    ):
        callsign = m.group(1).split(",")[0]
        dest     = m.group(2)
        ts       = m.group(3).replace(" ", "T")
        text     = re.sub(r'<[^>]+>', '', m.group(4)).strip()
        messages.append({
            "timestamp": local_to_utc(ts),
            "callsign":  callsign,
            "dest":      dest,
            "message":   text,
        })
    return messages

def save_status(db, data):
    db.execute("""INSERT INTO meshcom_status
        (timestamp, callsign, firmware, battery_v, battery_pct, wifi_rssi, gateway_on, uptime_start)
        VALUES (?,?,?,?,?,?,?,?)""",
        (now_utc(), data["callsign"], data["firmware"], data["battery_v"],
         data["battery_pct"], data["wifi_rssi"], data["gateway_on"], data["uptime_start"]))
    db.commit()

def save_mheard(db, nodes):
    for n in nodes:
        existing = db.execute(
            "SELECT timestamp FROM meshcom_mheard WHERE callsign=? ORDER BY id DESC LIMIT 1",
            (n["callsign"],)).fetchone()
        if existing and existing["timestamp"] >= n["timestamp"]:
            continue
        db.execute("""INSERT INTO meshcom_mheard
            (timestamp, callsign, rssi, snr, distance, lat, lon, alt, hardware, msg_type)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (n["timestamp"], n["callsign"], n["rssi"], n["snr"], n["distance"],
             n["lat"], n["lon"], n["alt"], n["hardware"], n["msg_type"]))
    db.commit()

def save_rxlog_and_packets(db, entries):
    for e in entries:
        try:
            db.execute("""INSERT OR IGNORE INTO meshcom_rxlog
                (timestamp, raw, src_call, dst_call, path, msg_type, rssi, snr)
                VALUES (?,?,?,?,?,?,?,?)""",
                (e["timestamp"], e["raw"], e["src_call"], e["dst_call"],
                 e["path"], e["msg_type"], e["rssi"], e["snr"]))
        except: pass
        # beacon posizione ora gestiti da meshcom-udp-listener.py (tempo reale)
    db.commit()

def save_messages(db, messages):
    row = db.execute("SELECT MAX(timestamp) FROM meshcom_messages").fetchone()
    last_ts = row[0] if row and row[0] else "2000-01-01T00:00:00"
    new_msgs = []
    for m in messages:
        if m["timestamp"] <= last_ts:
            continue
        try:
            cur = db.execute(
                "INSERT OR IGNORE INTO meshcom_messages (timestamp, callsign, dest, message) VALUES (?,?,?,?)",
                (m["timestamp"], m["callsign"], m["dest"], m["message"])
            )
            if cur.rowcount > 0:
                new_msgs.append(m)
        except Exception as e:
            log.warning(f"save_messages: {e}")
    db.commit()
    return new_msgs

def notify_message(m):
    try:
        dt = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S")
        time_str = dt.replace(tzinfo=timezone.utc).astimezone(ROME).strftime("%H:%M")
    except:
        time_str = m["timestamp"][11:16]
    dest_str = f" -> {m['dest']}" if m["dest"] and m["dest"] not in ("*", "222") else " -> ALL"
    msg = (
        "\U0001f4e1 MeshCom IU5MGF-12\n"
        + f"\U0001f4ac {m['callsign']}{dest_str}\n"
        + f"\U0001f4dd {m['message']}\n"
        + f"\u23f1 {time_str}"
    )
    send_notify(msg)
    log.info(f"Messaggio notificato: {m['callsign']}: {m['message'][:30]}")

def poll():
    db = get_db()
    log.info("Polling MeshCom node...")
    html_info = fetch("/")
    if html_info:
        info = parse_info(html_info)
        save_status(db, info)
        log.info(f"Status: batt={info['battery_v']}V ({info['battery_pct']}%) wifi={info['wifi_rssi']}dBm gw={info['gateway_on']}")
    html_mheard = fetch("/?page=mheard")
    if html_mheard:
        nodes = parse_mheard(html_mheard)
        save_mheard(db, nodes)
        log.info(f"MHeard: {len(nodes)} nodi")
    html_rxlog = fetch("/?page=rxlog")
    if html_rxlog:
        entries = parse_rxlog(html_rxlog)
        save_rxlog_and_packets(db, entries)
        pos = sum(1 for e in entries if e["lat"])
        log.info(f"RXLog: {len(entries)} entries, {pos} con posizione")
    html_msgs = fetch("/?getmessages")
    if html_msgs:
        messages = parse_messages(html_msgs)
        seen = set()
        unique = []
        for m in messages:
            key = (m["callsign"], m["message"])
            if key not in seen:
                seen.add(key)
                unique.append(m)
        # messaggi ora notificati da meshcom-udp-listener.py (tempo reale)
        # qui salviamo solo per storico, senza notifica duplicata
        new_msgs = save_messages(db, unique)
        log.info(f"Messaggi: {len(unique)} unici, {len(new_msgs)} nuovi (gia notificati via UDP)")
    db.close()

if __name__ == "__main__":
    log.info(f"meshcom-poller avviato -- nodo {MESHCOM_CALLSIGN} @ {MESHCOM_IP}")
    while True:
        try:
            poll()
        except Exception as e:
            log.error(f"Errore poll: {e}")
        time.sleep(60)
