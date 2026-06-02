import sqlite3
import time
import sys
import os
from datetime import datetime
import pytz

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import DB_PATH, TIMEZONE, DB_RETENTION_DAYS

ROME = pytz.timezone(TIMEZONE)
CHECK_INTERVAL = 3600

def cleanup():
    try:
        db = sqlite3.connect(DB_PATH)
        before = db.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        db.execute(f"DELETE FROM packets WHERE timestamp < datetime('now', '-{DB_RETENTION_DAYS} days')")
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

print(f"Avvio cleanup.py - retention {DB_RETENTION_DAYS} giorni", flush=True)
while True:
    cleanup()
    time.sleep(CHECK_INTERVAL)
