import sqlite3
import time
from datetime import datetime
import pytz

DB_PATH = "/mnt/ssd/radio/data/aprs.db"
ROME = pytz.timezone("Europe/Rome")
RETENTION_DAYS = 30
CHECK_INTERVAL = 3600  # controlla ogni ora

def cleanup():
    try:
        db = sqlite3.connect(DB_PATH)
        before = db.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        db.execute(f"DELETE FROM packets WHERE timestamp < datetime('now', '-{RETENTION_DAYS} days')")
        db.commit()
        after = db.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        deleted = before - after
        db.execute("VACUUM")
        db.commit()
        db.close()
        now = datetime.now(ROME).strftime("%Y-%m-%d %H:%M")
        print(f"[{now}] Cleanup: eliminati {deleted} record, rimasti {after}", flush=True)
    except Exception as e:
        print(f"Cleanup error: {e}", flush=True)

print("Avvio cleanup.py - retention 30 giorni", flush=True)

while True:
    cleanup()
    time.sleep(CHECK_INTERVAL)
