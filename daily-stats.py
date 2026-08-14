import sqlite3
import sys
from datetime import datetime, timedelta
import pytz

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, TIMEZONE, CALLSIGN

ROME = pytz.timezone(TIMEZONE)

def compute_day(date_str):
    day_start = ROME.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    day_end   = day_start + timedelta(days=1)
    ts_start  = day_start.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S")
    ts_end    = day_end.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S")
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    total = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND timestamp >= ? AND timestamp < ?", (ts_start, ts_end)).fetchone()[0]
    total_rf = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND path NOT LIKE '%*%' AND timestamp >= ? AND timestamp < ?", (ts_start, ts_end)).fetchone()[0]
    total_digi = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND path LIKE '%*%' AND timestamp >= ? AND timestamp < ?", (ts_start, ts_end)).fetchone()[0]
    unique = db.execute("SELECT COUNT(DISTINCT callsign) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ? AND timestamp >= ? AND timestamp < ?", (CALLSIGN, ts_start, ts_end)).fetchone()[0]
    best = db.execute("SELECT callsign, MAX(distance) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND distance IS NOT NULL AND path NOT LIKE '%*%' AND callsign != ? AND timestamp >= ? AND timestamp < ?", (CALLSIGN, ts_start, ts_end)).fetchone()
    rssi_avg = db.execute("SELECT AVG(rssi) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND rssi IS NOT NULL AND timestamp >= ? AND timestamp < ?", (ts_start, ts_end)).fetchone()[0]
    crc = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=0 AND timestamp >= ? AND timestamp < ?", (ts_start, ts_end)).fetchone()[0]
    peak = db.execute("SELECT strftime('%H', timestamp) as hr, COUNT(*) as cnt FROM packets WHERE crc_ok=1 AND msg_type='RX' AND timestamp >= ? AND timestamp < ? GROUP BY hr ORDER BY cnt DESC LIMIT 1", (ts_start, ts_end)).fetchone()
    db.execute("""INSERT OR REPLACE INTO daily_stats
        (date, total_packets, total_rf, total_digi, unique_stations,
         best_distance, best_callsign, rssi_avg, crc_errors, peak_hour)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (date_str, total, total_rf, total_digi, unique,
         round(best[1], 1) if best and best[1] else None,
         best[0] if best else None,
         round(rssi_avg, 1) if rssi_avg else None,
         crc, peak[0] if peak else None))
    db.commit()
    db.close()
    print(f"daily_stats: {date_str} — pkt:{total} rf:{total_rf} digi:{total_digi} uniche:{unique}", flush=True)

db = sqlite3.connect(DB_PATH)
dates = db.execute("""SELECT DISTINCT date(datetime(timestamp, '+2 hours')) as d
    FROM packets WHERE crc_ok=1 AND msg_type='RX' ORDER BY d""").fetchall()
db.close()
today = datetime.now(ROME).strftime("%Y-%m-%d")
for row in dates:
    d = row[0]
    if d and d < today:
        compute_day(d)
print("Importazione storica completata.", flush=True)
