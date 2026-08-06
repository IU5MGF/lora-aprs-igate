import socket
import sqlite3
import re
import sys
from datetime import datetime

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, CALLSIGN

HOST = "0.0.0.0"
PORT = 1514

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS packets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, msg_type TEXT, callsign TEXT, path TEXT,
        crc_ok INTEGER, rssi REAL, snr REAL, freq_err REAL,
        distance REAL, lat REAL, lon REAL, comment TEXT, raw TEXT, voltage REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS stations (
        callsign TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT,
        total_packets INTEGER, max_distance REAL, max_distance_date TEXT,
        best_rssi REAL, last_rssi REAL, last_lat REAL, last_lon REAL, last_path TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
        date TEXT PRIMARY KEY, total_packets INTEGER, total_rf INTEGER,
        total_digi INTEGER, unique_stations INTEGER, best_distance REAL,
        best_callsign TEXT, rssi_avg REAL, crc_errors INTEGER, peak_hour TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS system_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
        cpu_temp REAL, ram_used INTEGER, ram_total INTEGER,
        disk_used INTEGER, disk_total INTEGER, uptime_seconds INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, type TEXT, message TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS coverage_points (
        callsign TEXT PRIMARY KEY,
        lat REAL, lon REAL, timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meshcom_weather (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, callsign TEXT,
        temp REAL, hum REAL, qfe REAL, qnh REAL, gas REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meshcom_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        callsign TEXT,
        firmware TEXT,
        battery_v REAL,
        battery_pct INTEGER,
        wifi_rssi INTEGER,
        gateway_on INTEGER,
        uptime_start TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meshcom_mheard (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        callsign TEXT,
        rssi INTEGER,
        snr INTEGER,
        distance REAL,
        lat REAL,
        lon REAL,
        alt INTEGER,
        hardware TEXT,
        msg_type TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meshcom_rxlog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        raw TEXT UNIQUE,
        src_call TEXT,
        dst_call TEXT,
        path TEXT,
        msg_type TEXT,
        rssi INTEGER,
        snr INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meshcom_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        callsign TEXT,
        dest TEXT,
        message TEXT,
        UNIQUE(timestamp, callsign, message)
    )''')
    conn.commit()
    conn.close()
    print("DB inizializzato", flush=True)
def parse_syslog(line):
    try:
        if ' - - - ' not in line:
            return None
        line = line.split(' - - - ', 1)[1]
        parts = [p.strip() for p in line.split(' / ')]
        msg_type = parts[0] if len(parts) > 0 else None
        if msg_type == 'MESSAGE':
            return None
        if msg_type == 'TX':
            raw_packet = parts[1] if len(parts) > 1 else None
            if not raw_packet or '>' not in raw_packet or ':' not in raw_packet:
                return None
            callsign = raw_packet.split('>', 1)[0].strip()
            rest = raw_packet.split('>', 1)[1]
            tx_path = rest.split(':', 1)[0].strip()
            comment = rest.split(':', 1)[1] if ':' in rest else None
            voltage = None
            if comment:
                volt_match = re.search(r'\|.{2}(.{2})\|', comment)
                if volt_match:
                    t = volt_match.group(1)
                    try:
                        v_raw = (ord(t[0]) - 33) * 91 + (ord(t[1]) - 33)
                        voltage = round(v_raw * 0.01, 2)
                    except: pass
                comment = re.sub(r'\|[^|]+\|$', '', comment).strip() or None
            return msg_type, callsign, tx_path, 1, None, None, None, None, None, None, comment, voltage
        crc_ok = 0 if msg_type == 'CRC' else 1
        raw_call = parts[2] if len(parts) > 2 else None
        callsign = raw_call if raw_call and re.match(r'^[A-Z0-9]{3,8}(-\d{1,2})?$', raw_call) else None
        path = parts[3] if len(parts) > 3 else None
        # Fallback: pacchetti terza parte con payload APRS annidato (} = third-party)
        if not callsign:
            # Isola il payload dopo "RX / " per evitare di matchare l'header syslog <165>
            payload_part = line.split(' / ', 1)[1] if ' / ' in line else line
            tp = re.search(r'\}([A-Z0-9]{3,8}(?:-[A-Z0-9]{1,2})?)>', payload_part)
            if tp:
                callsign = tp.group(1)
                # Trasmittente RF diretto del frame esterno: <CALLSIGN>...
                src_match = re.search(r'<.{0,3}?([A-Z0-9]{3,8}(?:-[A-Z0-9]{1,2})?)>', payload_part)
                # Path esterno con digipeater intermedio (DEST,PATH*:})
                ext_path = re.search(r'>[A-Z0-9]+,([A-Z0-9,*\-]+):\}', payload_part)
                if ext_path:
                    path = ext_path.group(1)
                elif src_match:
                    # Nessun digipeater intermedio: il trasmittente RF è la sorgente diretta
                    path = src_match.group(1) + '*'
        rssi     = float(parts[5].replace('dBm',''))  if len(parts) > 5  and 'dBm' in parts[5]  else None
        snr      = float(parts[6].replace('dB',''))   if len(parts) > 6  and 'dB'  in parts[6]  else None
        freq_err = float(parts[7].replace('Hz',''))   if len(parts) > 7  and 'Hz'  in parts[7]  else None
        # Fallback RSSI/SNR/FREQ dalla fine se shiftati (pacchetti terza parte)
        if rssi is None:
            m = re.search(r'/\s*(-?\d+(?:\.\d+)?)dBm', line)
            if m: rssi = float(m.group(1))
        if snr is None:
            m = re.search(r'/\s*(-?\d+(?:\.\d+)?)dB\b', line)
            if m: snr = float(m.group(1))
        if freq_err is None:
            m = re.search(r'/\s*(-?\d+(?:\.\d+)?)Hz\s*$', line)
            if m: freq_err = float(m.group(1))
        distance = float(parts[10].replace('km',''))  if len(parts) > 10 and 'km'  in parts[10] else None
        lat = lon = None
        if len(parts) > 8 and 'N' in parts[8]:
            try:
                lat = float(parts[8].replace('N','').replace('S',''))
                if 'S' in parts[8]: lat = -lat
            except: pass
        if len(parts) > 9 and ('E' in parts[9] or 'W' in parts[9]):
            try:
                lon = float(parts[9].replace('E','').replace('W',''))
                if 'W' in parts[9]: lon = -lon
            except: pass
        # Fallback lat/lon da regex per pacchetti terza parte
        if lat is None:
            m = re.search(r'(\d{2})(\d{2}\.\d+)([NS])', line)
            if m:
                lat = int(m.group(1)) + float(m.group(2))/60
                if m.group(3) == 'S': lat = -lat
        if lon is None:
            m = re.search(r'(\d{3})(\d{2}\.\d+)([EW])', line)
            if m:
                lon = int(m.group(1)) + float(m.group(2))/60
                if m.group(3) == 'W': lon = -lon
        comment = parts[11] if len(parts) > 11 else None
        voltage = None
        if comment:
            volt_match = re.search(r'\|.{2}(.{2})\|', comment)
            if volt_match:
                t = volt_match.group(1)
                try:
                    v_raw = (ord(t[0]) - 33) * 91 + (ord(t[1]) - 33)
                    voltage = round(v_raw * 0.01, 2)
                except: pass
            comment = re.sub(r'\|[^|]+\|$', '', comment).strip() or None
        return msg_type, callsign, path, crc_ok, rssi, snr, freq_err, distance, lat, lon, comment, voltage
    except Exception as e:
        print(f"Parse error: {e} | {line}", flush=True)
        return None
def update_station(callsign, timestamp, distance, rssi, lat, lon, path):
    try:
        db = sqlite3.connect(DB_PATH)
        existing = db.execute(
            'SELECT total_packets, max_distance, best_rssi FROM stations WHERE callsign=?',
            (callsign,)
        ).fetchone()
        if existing:
            total = existing[0] + 1
            max_dist = existing[1]
            best_rssi = existing[2]
            max_dist_date = None
            if distance and path and '*' not in path and not (lat == 0 and lon == 0):
                if max_dist is None or distance > max_dist:
                    max_dist = distance
                    max_dist_date = timestamp
            if rssi and (best_rssi is None or rssi > best_rssi):
                best_rssi = rssi
            db.execute(
                """UPDATE stations SET last_seen=?, total_packets=?, max_distance=?,
                best_rssi=?, last_rssi=?, last_lat=?, last_lon=?, last_path=?,
                max_distance_date=COALESCE(?,max_distance_date) WHERE callsign=?""",
                (timestamp, total, max_dist, best_rssi, rssi, lat, lon, path, max_dist_date, callsign)
            )
        else:
            max_dist = distance if path and '*' not in path and not (lat == 0 and lon == 0) else None
            db.execute(
                """INSERT INTO stations (callsign, first_seen, last_seen, total_packets,
                max_distance, max_distance_date, best_rssi, last_rssi, last_lat, last_lon, last_path)
                VALUES (?,?,?,1,?,?,?,?,?,?,?)""",
                (callsign, timestamp, timestamp, max_dist,
                 timestamp if max_dist else None, rssi, rssi, lat, lon, path)
            )
        db.commit()
        db.close()
    except Exception as e:
        print(f"Station update error: {e}", flush=True)

def main():
    init_db()
    print(f"Listening on UDP {HOST}:{PORT}", flush=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    while True:
        data, addr = sock.recvfrom(4096)
        lines = data.decode("utf-8", errors="replace").split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            print(f"RX: {line}", flush=True)
            result = parse_syslog(line)
            if result is None:
                continue
            msg_type, callsign, path, crc_ok, rssi, snr, freq_err, distance, lat, lon, comment, voltage = result
            ts = datetime.utcnow().isoformat()
            try:
                db = sqlite3.connect(DB_PATH, timeout=10)
                db.execute(
                    "INSERT INTO packets VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ts, msg_type, callsign, path, crc_ok, rssi, snr, freq_err,
                     distance, lat, lon, comment, line, voltage)
                )
                db.commit()
                db.close()
            except Exception as e:
                print(f"Packet insert error: {e}", flush=True)
                continue
            if callsign and callsign != CALLSIGN and msg_type == 'RX' and crc_ok == 1:
                update_station(callsign, ts, distance, rssi, lat, lon, path)
                # Aggiorna coverage_points per RF diretta (no digi, no meshcom)
                if lat and lon and path and '*' not in path and path != 'MESHCOM' and distance and distance < 500:
                    try:
                        db2 = sqlite3.connect(DB_PATH)
                        db2.execute(
                            "INSERT OR REPLACE INTO coverage_points (callsign, lat, lon, timestamp) VALUES (?,?,?,?)",
                            (callsign, lat, lon, ts)
                        )
                        db2.commit()
                        db2.close()
                    except Exception as ce:
                        print(f"Coverage update error: {ce}", flush=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init-only":
        init_db()
        sys.exit(0)
    main()
