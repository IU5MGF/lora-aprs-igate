from flask import Flask, jsonify, render_template_string
import sqlite3
from datetime import datetime, timezone
import os
import pytz

app = Flask(__name__, static_folder="/mnt/ssd/radio/flask-dashboard", static_url_path="/static")
DB_PATH = "/mnt/ssd/radio/data/aprs.db"
ROME = pytz.timezone("Europe/Rome")

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

@app.route("/map")
def map_page():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/map.html").read())

@app.route("/")
def index():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/index.html").read())

@app.route("/api/stats")
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours')").fetchone()[0]
    unique = db.execute("SELECT COUNT(DISTINCT callsign) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours')").fetchone()[0]
    best = db.execute("SELECT callsign, MAX(distance) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND distance IS NOT NULL AND path NOT LIKE '%*%' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours')").fetchone()
    rssi_avg = db.execute("SELECT AVG(rssi) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND rssi IS NOT NULL AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours')").fetchone()[0]
    crc_errors = db.execute("SELECT COUNT(*) FROM packets WHERE crc_ok=0 AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours')").fetchone()[0]
    db.close()
    return jsonify({"total": total, "unique": unique, "best_callsign": best[0] if best else "-", "best_distance": best[1] if best else 0, "rssi_avg": round(rssi_avg, 1) if rssi_avg else 0, "crc_errors": crc_errors})

@app.route("/api/packets")
def packets():
    db = get_db()
    rows = db.execute("SELECT timestamp, callsign, path, rssi, snr, distance, comment FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER' ORDER BY id DESC LIMIT 50").fetchall()
    db.close()
    result = []
    for r in rows:
        try:
            dt_utc = datetime.strptime(r["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            time_str = dt_utc.astimezone(ROME).strftime("%H:%M:%S")
        except:
            time_str = r["timestamp"][11:19] if r["timestamp"] else "-"
        result.append({"time": time_str, "callsign": r["callsign"], "path": r["path"] or "-", "rssi": r["rssi"], "snr": r["snr"], "distance": r["distance"], "comment": r["comment"] or ""})
    return jsonify(result)

@app.route("/api/top_stations")
def top_stations():
    db = get_db()
    rows = db.execute("SELECT callsign, COUNT(*) as cnt, MAX(distance) as max_dist, AVG(rssi) as avg_rssi FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER' AND path NOT LIKE '%*%' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours') GROUP BY callsign ORDER BY cnt DESC LIMIT 10").fetchall()
    db.close()
    return jsonify([{"callsign": r["callsign"], "count": r["cnt"], "max_distance": round(r["max_dist"], 1) if r["max_dist"] else 0, "avg_rssi": round(r["avg_rssi"], 1) if r["avg_rssi"] else 0} for r in rows])

@app.route("/api/hourly")
def hourly():
    db = get_db()
    rows = db.execute("SELECT strftime('%H', datetime(timestamp, '+2 hours')) as hr, COUNT(*) as cnt FROM packets WHERE crc_ok=1 AND msg_type='RX' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours') GROUP BY hr ORDER BY hr").fetchall()
    db.close()
    data = {str(h).zfill(2): 0 for h in range(24)}
    for r in rows:
        data[r["hr"]] = r["cnt"]
    return jsonify(data)

@app.route("/api/map")
def map_data():
    db = get_db()
    rows = db.execute("""
        SELECT callsign, lat, lon, rssi, distance, timestamp, path
        FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER'
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp, 'T', ' ') >= datetime('now', '-60 minutes')
        AND id IN (
            SELECT MAX(id) FROM packets
            WHERE crc_ok=1 AND msg_type='RX'
            AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER'
            AND lat IS NOT NULL AND lon IS NOT NULL
            AND replace(timestamp, 'T', ' ') >= datetime('now', '-60 minutes')
            GROUP BY callsign
        )
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        tipo = 'digi' if r['path'] and '*' in r['path'] else 'rf'
        result.append({
            "callsign": r["callsign"],
            "lat": r["lat"],
            "lon": r["lon"],
            "rssi": r["rssi"],
            "distance": r["distance"],
            "type": tipo,
            "last_ts": r["timestamp"]
        })
    return jsonify(result)

@app.route("/api/tracks")
def tracks():
    db = get_db()
    # trova callsign con piu di 5 posizioni distinte nelle ultime 24h
    trackers = db.execute("""SELECT callsign FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND path NOT LIKE '%*%'
        AND replace(timestamp, 'T', ' ') >= datetime('now', '-60 minutes') AND date(timestamp, '+2 hours') = date('now', '+2 hours')
        GROUP BY callsign
        HAVING COUNT(*) > 2 AND (MAX(lat)-MIN(lat) > 0.001 OR MAX(lon)-MIN(lon) > 0.001)""").fetchall()
    # tutti i tracker (RF + digi combinati)
    all_trackers = db.execute("""SELECT callsign FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp, 'T', ' ') >= datetime('now', '-60 minutes') AND date(timestamp, '+2 hours') = date('now', '+2 hours')
        GROUP BY callsign
        HAVING COUNT(*) > 2 AND (MAX(lat)-MIN(lat) > 0.001 OR MAX(lon)-MIN(lon) > 0.001)""").fetchall()
    result = {}
    for t in all_trackers:
        call = t['callsign']
        # prendi tutti i punti (RF e digi) ordinati per tempo
        points = db.execute("""SELECT lat, lon, rssi, timestamp, path FROM packets
            WHERE crc_ok=1 AND msg_type='RX'
            AND callsign=? AND lat IS NOT NULL AND lon IS NOT NULL
            AND replace(timestamp, 'T', ' ') >= datetime('now', '-60 minutes') AND date(timestamp, '+2 hours') = date('now', '+2 hours')
            ORDER BY timestamp ASC""", (call,)).fetchall()
        if not points:
            continue
        # tipo basato sull'ULTIMO pacchetto ricevuto
        last_path = points[-1]['path'] or ''
        tipo = 'digi' if '*' in last_path else 'rf'
        result[call] = {
            'type': tipo,
            'points': [{'lat': p['lat'], 'lon': p['lon'], 'rssi': p['rssi'], 'time': (lambda ts: __import__('datetime').datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=__import__('datetime').timezone.utc).astimezone(__import__('pytz').timezone('Europe/Rome')).strftime('%H:%M'))(p['timestamp'])} for p in points]
        }
    db.close()
    return jsonify(result)

@app.route("/api/heatmap")
def heatmap():
    db = get_db()
    rows = db.execute("""
        SELECT lat, lon, rssi FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND path NOT LIKE '%*%'
        AND date(timestamp, '+2 hours') = date('now', '+2 hours')
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        intensity = max(0, min(1, (r['rssi'] + 150) / 50))
        result.append([r['lat'], r['lon'], intensity])
    return jsonify(result)


@app.route("/api/top_stations_digi")
def top_stations_digi():
    db = get_db()
    rows = db.execute("SELECT callsign, COUNT(*) as cnt, MAX(distance) as max_dist, AVG(rssi) as avg_rssi FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != 'CALLSIGN_PLACEHOLDER' AND path LIKE '%*%' AND replace(timestamp,'T',' ') >= datetime('now', '+2 hours', 'start of day', '-2 hours') GROUP BY callsign ORDER BY cnt DESC LIMIT 10").fetchall()
    db.close()
    return jsonify([{"callsign": r["callsign"], "count": r["cnt"], "max_distance": round(r["max_dist"], 1) if r["max_dist"] else 0, "avg_rssi": round(r["avg_rssi"], 1) if r["avg_rssi"] else 0} for r in rows])

@app.route("/stations")
def stations_page():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/stations.html").read())

@app.route("/api/stations")
def stations_api():
    db = get_db()
    rows = db.execute("""SELECT callsign, first_seen, last_seen, total_packets,
        max_distance, max_distance_date, best_rssi, last_rssi, last_lat, last_lon, last_path
        FROM stations ORDER BY total_packets DESC""").fetchall()
    db.close()
    result = []
    for r in rows:
        result.append({
            "callsign": r["callsign"],
            "first_seen": r["first_seen"][:10] if r["first_seen"] else "-",
            "last_seen": r["last_seen"][:16].replace("T"," ") if r["last_seen"] else "-",
            "total_packets": r["total_packets"],
            "max_distance": round(r["max_distance"],1) if r["max_distance"] else 0,
            "max_distance_date": r["max_distance_date"][:10] if r["max_distance_date"] else "-",
            "best_rssi": r["best_rssi"],
            "last_rssi": r["last_rssi"],
            "last_path": r["last_path"] or "-"
        })
    return jsonify(result)

@app.route("/api/stations_summary")
def stations_summary():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    best = db.execute("SELECT callsign, max_distance, max_distance_date FROM stations WHERE max_distance IS NOT NULL ORDER BY max_distance DESC LIMIT 1").fetchone()
    most = db.execute("SELECT callsign, total_packets FROM stations ORDER BY total_packets DESC LIMIT 1").fetchone()
    db.close()
    return jsonify({
        "total_stations": total,
        "best_callsign": best["callsign"] if best else "-",
        "best_distance": round(best["max_distance"],1) if best else 0,
        "best_date": best["max_distance_date"][:10] if best and best["max_distance_date"] else "-",
        "most_callsign": most["callsign"] if most else "-",
        "most_packets": most["total_packets"] if most else 0
    })

@app.route("/api/igate_beacon")
def igate_beacon():
    db = get_db()
    row = db.execute("""SELECT timestamp FROM packets
        WHERE callsign='CALLSIGN_PLACEHOLDER' AND msg_type='RX'
        ORDER BY id DESC LIMIT 1""").fetchone()
    db.close()
    if row:
        from datetime import datetime, timezone
        import pytz
        last_ts = datetime.strptime(row["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        minutes_ago = int((datetime.now(timezone.utc) - last_ts).total_seconds() / 60)
        rome = pytz.timezone("Europe/Rome")
        time_str = last_ts.astimezone(rome).strftime("%H:%M")
        return jsonify({"time": time_str, "minutes_ago": minutes_ago, "online": minutes_ago < 15})
    return jsonify({"time": "-", "minutes_ago": 999, "online": False})

@app.route("/stats")
def stats_page():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/stats.html").read())

@app.route("/api/daily_stats")
def daily_stats_api():
    db = get_db()
    rows = db.execute("""SELECT date, total_packets, total_rf, total_digi,
        unique_stations, best_distance, best_callsign, rssi_avg, crc_errors, peak_hour
        FROM daily_stats ORDER BY date DESC""").fetchall()
    db.close()
    result = []
    for r in rows:
        result.append({
            "date": r["date"],
            "total_packets": r["total_packets"],
            "total_rf": r["total_rf"],
            "total_digi": r["total_digi"],
            "unique_stations": r["unique_stations"],
            "best_distance": r["best_distance"],
            "best_callsign": r["best_callsign"] or "-",
            "rssi_avg": r["rssi_avg"],
            "crc_errors": r["crc_errors"],
            "peak_hour": r["peak_hour"] or "-"
        })
    return jsonify(result)

@app.route("/server")
def server_page():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/server.html").read())

@app.route("/api/system_stats")
def system_stats_api():
    db = get_db()
    rows = db.execute("""SELECT timestamp, cpu_temp, ram_used, ram_total, disk_used, disk_total, uptime_seconds, cpu_perc, cpu_freq, net_rx, net_tx
        FROM system_stats ORDER BY id DESC LIMIT 168""").fetchall()
    db.close()
    import pytz
    rome = pytz.timezone("Europe/Rome")
    result = []
    for r in rows:
        try:
            from datetime import datetime, timezone
            dt = datetime.strptime(r["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            time_str = dt.astimezone(rome).strftime("%d/%m %H:%M")
        except:
            time_str = r["timestamp"][:16]
        result.append({
            "time": time_str,
            "cpu_temp": r["cpu_temp"],
            "cpu_perc": r["cpu_perc"],
            "cpu_freq": r["cpu_freq"],
            "ram_used": r["ram_used"],
            "ram_total": r["ram_total"],
            "ram_perc": round(r["ram_used"]/r["ram_total"]*100, 1) if r["ram_total"] else 0,
            "disk_used": r["disk_used"],
            "disk_total": r["disk_total"],
            "disk_perc": round(r["disk_used"]/r["disk_total"]*100, 1) if r["disk_total"] else 0,
            "uptime": r["uptime_seconds"],
            "net_rx": r["net_rx"],
            "net_tx": r["net_tx"]
        })
    # uptime live
    try:
        live_uptime = int(float(open("/proc/uptime").read().split()[0]))
    except:
        live_uptime = None
    return jsonify({"data": list(reversed(result)), "live_uptime": live_uptime})



@app.route("/api/reboot", methods=["POST"])
def reboot():
    import subprocess
    from flask import request
    password = request.json.get("password", "")
    target = request.json.get("target", "server")
    if password != "REBOOT_PWD_PLACEHOLDER":
        return jsonify({"ok": False, "msg": "Password errata"})
    # verifica password
    try:
        import subprocess as sp
        result = sp.run(["sudo", "-S", "true"], input=password+"\n", capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({"ok": False, "msg": "Password errata"})
    except:
        return jsonify({"ok": False, "msg": "Errore verifica password"})
    if target == "igate":
        try:
            import requests as req
            req.post("http://IGATE_IP_PLACEHOLDER/action?type=reboot", timeout=5)
            return jsonify({"ok": True, "msg": "iGate riavviato"})
        except Exception as e:
            if "Connection" in str(e) or "reset" in str(e).lower() or "RemoteDisconnected" in str(e):
                return jsonify({"ok": True, "msg": "iGate riavviato"})
            return jsonify({"ok": False, "msg": "iGate non raggiungibile"})
    else:
        subprocess.Popen(["sudo", "reboot"])
        return jsonify({"ok": True, "msg": "Server in riavvio..."})

@app.route("/events")
def events_page():
    return render_template_string(open("/mnt/ssd/radio/flask-dashboard/events.html").read())

@app.route("/api/events")
def events_api():
    db = get_db()
    rows = db.execute("""SELECT id, timestamp, type, message
        FROM events ORDER BY id DESC LIMIT 100""").fetchall()
    db.close()
    import pytz
    rome = pytz.timezone("Europe/Rome")
    from datetime import datetime, timezone
    result = []
    for r in rows:
        try:
            dt = datetime.strptime(r["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            time_str = dt.astimezone(rome).strftime("%d/%m %H:%M")
        except:
            time_str = r["timestamp"][:16]
        result.append({"id": r["id"], "time": time_str, "type": r["type"], "message": r["message"]})
    return jsonify(result)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
