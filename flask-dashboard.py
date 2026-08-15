from flask import Flask, jsonify, render_template_string, request
import sqlite3
import threading
import subprocess
import math
import requests as req
from datetime import datetime, timezone
import os
import sys
import pytz

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import (
    CALLSIGN, DB_PATH, TIMEZONE, DATA_DIR,
    IGATE_IP, IGATE_REBOOT_PW, HAS_SSD, SSD_MOUNT,
    LATITUDE, LONGITUDE
)
try:
    from config import HAS_MESHCOM, MESHCOM_CALLSIGN
except ImportError:
    HAS_MESHCOM = False
    MESHCOM_CALLSIGN = ""

DASHBOARD_DIR = os.path.join(os.path.dirname(DATA_DIR), "flask-dashboard")

app = Flask(__name__, static_folder=DASHBOARD_DIR, static_url_path="/static")

@app.route('/api/disk_space')
def disk_space():
    import shutil
    total, used, free = shutil.disk_usage("/")
    return jsonify({
        'total_gb': round(total / (1024**3), 1),
        'used_gb': round(used / (1024**3), 1),
        'free_gb': round(free / (1024**3), 1),
        'percent_used': round((used / total) * 100, 1)
    })

ROME = pytz.timezone(TIMEZONE)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def rome_time(ts):
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(ROME)
    except:
        return None

@app.route("/")
def index():
    return render_template_string(open(f"{DASHBOARD_DIR}/index.html").read(), callsign=CALLSIGN)

@app.route("/map")
def map_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/map.html").read(), callsign=CALLSIGN, lat=LATITUDE, lon=LONGITUDE)

@app.route("/stations")
def stations_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/stations.html").read(), callsign=CALLSIGN)

@app.route("/stats")
def stats_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/stats.html").read(), callsign=CALLSIGN)

@app.route("/server")
def server_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/server.html").read(), callsign=CALLSIGN)

@app.route("/events")
def events_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/events.html").read(), callsign=CALLSIGN)
@app.route("/api/stats")
def stats():
    db = get_db()
    since = "datetime('now', '+2 hours', 'start of day', '-2 hours')"
    total      = db.execute(f"SELECT COUNT(*) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND replace(timestamp,'T',' ') >= {since}").fetchone()[0]
    unique     = db.execute(f"SELECT COUNT(DISTINCT callsign) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ? AND replace(timestamp,'T',' ') >= {since}", (CALLSIGN,)).fetchone()[0]
    best       = db.execute(f"SELECT callsign, MAX(distance) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND distance IS NOT NULL AND path NOT LIKE '%*%' AND replace(timestamp,'T',' ') >= {since}").fetchone()
    rssi_avg   = db.execute(f"SELECT AVG(rssi) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND rssi IS NOT NULL AND replace(timestamp,'T',' ') >= {since}").fetchone()[0]
    crc_errors = db.execute(f"SELECT COUNT(*) FROM packets WHERE crc_ok=0 AND replace(timestamp,'T',' ') >= {since}").fetchone()[0]
    meshcom_packets = 0
    try:
        meshcom_packets = db.execute(
            "SELECT COUNT(*) FROM meshcom_rxlog WHERE replace(timestamp,'T',' ') >= datetime('now', '-24 hours')"
        ).fetchone()[0]
    except: pass
    db.close()
    return jsonify({"total": total, "unique": unique,
        "best_callsign": best[0] if best else "-",
        "best_distance": best[1] if best else 0,
        "rssi_avg": round(rssi_avg, 1) if rssi_avg else 0,
        "crc_errors": crc_errors,
        "meshcom_packets": meshcom_packets})

@app.route("/api/packets")
def packets():
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, callsign, path, rssi, snr, distance, comment FROM packets
        WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL
        ORDER BY id DESC LIMIT 50
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({"time": rt.strftime("%H:%M:%S") if rt else "-",
            "callsign": r["callsign"], "path": r["path"] or "-",
            "rssi": r["rssi"], "snr": r["snr"],
            "distance": r["distance"], "comment": r["comment"] or ""})
    return jsonify(result)

@app.route("/api/top_stations")
def top_stations():
    db = get_db()
    since = "datetime('now', '+2 hours', 'start of day', '-2 hours')"
    rows = db.execute(
        f"SELECT callsign, COUNT(*) as cnt, MAX(distance) as max_dist, AVG(rssi) as avg_rssi "
        f"FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ? "
        f"AND path NOT LIKE '%*%' AND replace(timestamp,'T',' ') >= {since} "
        f"GROUP BY callsign ORDER BY cnt DESC LIMIT 10", (CALLSIGN,)
    ).fetchall()
    db.close()
    return jsonify([{"callsign": r["callsign"], "count": r["cnt"],
        "max_distance": round(r["max_dist"], 1) if r["max_dist"] else 0,
        "avg_rssi": round(r["avg_rssi"], 1) if r["avg_rssi"] else 0} for r in rows])

@app.route("/api/top_stations_digi")
def top_stations_digi():
    db = get_db()
    since = "datetime('now', '+2 hours', 'start of day', '-2 hours')"
    rows = db.execute(
        f"SELECT callsign, COUNT(*) as cnt, MAX(distance) as max_dist, AVG(rssi) as avg_rssi "
        f"FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ? "
        f"AND path LIKE '%*%' AND replace(timestamp,'T',' ') >= {since} "
        f"GROUP BY callsign ORDER BY cnt DESC LIMIT 10", (CALLSIGN,)
    ).fetchall()
    db.close()
    return jsonify([{"callsign": r["callsign"], "count": r["cnt"],
        "max_distance": round(r["max_dist"], 1) if r["max_dist"] else 0,
        "avg_rssi": round(r["avg_rssi"], 1) if r["avg_rssi"] else 0} for r in rows])

@app.route("/api/hourly")
def hourly():
    db = get_db()
    since = "datetime('now', '+2 hours', 'start of day', '-2 hours')"
    rows = db.execute(
        f"SELECT strftime('%H', datetime(timestamp, '+2 hours')) as hr, COUNT(*) as cnt "
        f"FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != '' AND callsign != ? AND replace(timestamp,'T',' ') >= {since} "
        f"GROUP BY hr ORDER BY hr",
        (CALLSIGN,)
    ).fetchall()
    db.close()
    data = {str(h).zfill(2): 0 for h in range(24)}
    for r in rows:
        data[r["hr"]] = r["cnt"]
    return jsonify(data)
@app.route("/api/map")
def map_data():
    minutes = request.args.get("minutes", "60")
    try:
        minutes = int(minutes)
        if minutes not in (15, 30, 45, 60, 90, 120, 360, 720, 1440):
            minutes = 60
    except:
        minutes = 60
    db = get_db()
    own_callsigns = [CALLSIGN]
    try:
        from config import MESHCOM_CALLSIGN
        if MESHCOM_CALLSIGN:
            own_callsigns.append(MESHCOM_CALLSIGN)
    except: pass
    rows = db.execute("""
        SELECT callsign, lat, lon, rssi, distance, timestamp, path, voltage, comment
        FROM packets WHERE crc_ok=1 AND msg_type='RX'
        AND callsign IS NOT NULL AND callsign != ?
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' minutes')
        AND id IN (
            SELECT MAX(id) FROM packets
            WHERE crc_ok=1 AND msg_type='RX'
            AND callsign IS NOT NULL AND callsign != ?
            AND lat IS NOT NULL AND lon IS NOT NULL
            AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' minutes')
            GROUP BY callsign)
    """, (CALLSIGN, minutes, CALLSIGN, minutes)).fetchall()
    # aggiungi propri nodi
    own_rows = db.execute("""
        SELECT callsign, lat, lon, rssi, distance, timestamp, path, voltage, comment
        FROM packets WHERE callsign IN ({})
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp,'T',' ') >= datetime('now', '-180 minutes')
        AND id IN (SELECT MAX(id) FROM packets WHERE callsign IN ({})
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp,'T',' ') >= datetime('now', '-180 minutes') GROUP BY callsign)
    """.format(','.join('?'*len(own_callsigns)), ','.join('?'*len(own_callsigns))),
        own_callsigns + own_callsigns).fetchall()
    db.close()
    result = [{"callsign": r["callsign"], "lat": r["lat"], "lon": r["lon"],
        "rssi": r["rssi"], "distance": r["distance"],
        "type": 'meshcom' if r['path'] == 'MESHCOM' else ('digi' if r['path'] and '*' in r['path'] else 'rf'),
        "path": r["path"] or "",
        "voltage": r["voltage"],
        "comment": r["comment"] or "",
        "last_ts": r["timestamp"]} for r in rows]
    for r in own_rows:
        result.append({"callsign": r["callsign"], "lat": r["lat"], "lon": r["lon"],
            "rssi": r["rssi"], "distance": r["distance"],
            "type": "own", "voltage": r["voltage"], "comment": r["comment"] or "", "last_ts": r["timestamp"]})
    return jsonify(result)

@app.route("/api/voltage")
def voltage_history():
    days = request.args.get("days", "7")
    try:
        days = int(days)
        if days not in (1, 3, 7, 14, 30):
            days = 7
    except:
        days = 7
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, voltage FROM packets
        WHERE callsign=? AND voltage IS NOT NULL
        AND voltage > 3 AND voltage < 5
        AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' days')
        ORDER BY timestamp ASC
    """, (CALLSIGN, days)).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({
            "time": rt.strftime("%d/%m %H:%M") if rt else r["timestamp"][:16],
            "voltage": r["voltage"]
        })
    return jsonify(result)
@app.route("/api/coverage")
def coverage():
    db = get_db()
    rows = db.execute("SELECT lat, lon FROM coverage_points").fetchall()
    db.close()
    raw_points = [[r["lat"], r["lon"]] for r in rows]
    # Filtro anti-outlier: escludi il 5% dei punti piu lontani (stesso
    # principio usato da aprs.to) prima di calcolare il convex hull,
    # cosi un singolo DX eccezionale non fa esplodere il poligono
    if len(raw_points) >= 20:
        distances = sorted(
            haversine_km(LATITUDE, LONGITUDE, p[0], p[1]) for p in raw_points
        )
        idx95 = int(len(distances) * 0.95)
        threshold = distances[idx95]
        points = [p for p in raw_points
                  if haversine_km(LATITUDE, LONGITUDE, p[0], p[1]) <= threshold]
    else:
        points = raw_points
    points.append([LATITUDE, LONGITUDE])
    if len(points) < 3:
        return jsonify([])
    def cross(O, A, B):
        return (A[0]-O[0])*(B[1]-O[1]) - (A[1]-O[1])*(B[0]-O[0])
    pts = sorted(set(map(tuple, points)))
    if len(pts) < 3:
        return jsonify([list(p) for p in pts])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return jsonify([list(p) for p in hull])
@app.route("/api/stations/coords")
def stations_coords():
    db = get_db()
    rows = db.execute("SELECT callsign, last_lat, last_lon FROM stations WHERE last_lat IS NOT NULL AND last_lon IS NOT NULL").fetchall()
    db.close()
    result = {r["callsign"]: {"lat": r["last_lat"], "lon": r["last_lon"]} for r in rows}
    result[CALLSIGN] = {"lat": LATITUDE, "lon": LONGITUDE}
    return jsonify(result)
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

@app.route("/api/tracks")
def tracks():
    minutes = request.args.get("minutes", "60")
    try:
        minutes = int(minutes)
        if minutes not in (15, 30, 45, 60, 90, 120, 360, 720, 1440):
            minutes = 60
    except:
        minutes = 60
    db = get_db()
    all_trackers = db.execute("""
        SELECT callsign FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' minutes')
        GROUP BY callsign
        HAVING COUNT(*) > 2
        AND (MAX(lat)-MIN(lat) > 0.001 OR MAX(lon)-MIN(lon) > 0.001)
    """, (minutes,)).fetchall()
    result = {}
    for t in all_trackers:
        call = t['callsign']
        points = db.execute("""
            SELECT lat, lon, rssi, timestamp, path FROM (
                SELECT lat, lon, rssi, timestamp, path,
                    ROW_NUMBER() OVER (PARTITION BY lat, lon ORDER BY timestamp ASC) as rn
                FROM packets
                WHERE crc_ok=1 AND msg_type='RX' AND callsign=?
                AND lat IS NOT NULL AND lon IS NOT NULL
                AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' minutes')
            ) WHERE rn = 1
            ORDER BY timestamp ASC
        """, (call, minutes)).fetchall()
        if not points:
            continue

        # Filtro velocita impossibile: scarta punti che implicherebbero
        # una velocita > 500 km/h rispetto all'ultimo punto accettato
        # (stesso principio usato da aprs.fi per filtrare GPS/out-of-order)
        accepted = []
        for p in points:
            if p['lat'] == 0 and p['lon'] == 0:
                continue
            if not accepted:
                accepted.append(p)
                continue
            last = accepted[-1]
            try:
                t1 = datetime.fromisoformat(last['timestamp'])
                t2 = datetime.fromisoformat(p['timestamp'])
                dt_hours = (t2 - t1).total_seconds() / 3600.0
                if dt_hours <= 0:
                    continue
                dist_km = haversine_km(last['lat'], last['lon'], p['lat'], p['lon'])
                speed_kmh = dist_km / dt_hours
                if speed_kmh > 500:
                    continue
            except Exception:
                pass
            accepted.append(p)

        if not accepted:
            continue
        last_path = accepted[-1]['path'] or ''
        result[call] = {
            'type': 'digi' if '*' in last_path else 'rf',
            'points': [{'lat': p['lat'], 'lon': p['lon'], 'rssi': p['rssi'],
                'time': rome_time(p['timestamp']).strftime('%H:%M') if rome_time(p['timestamp']) else '-'}
                for p in accepted]}
    db.close()
    return jsonify(result)

@app.route("/api/heatmap")
def heatmap():
    db = get_db()
    rows = db.execute("""SELECT lat, lon, rssi FROM packets
        WHERE crc_ok=1 AND msg_type='RX'
        AND lat IS NOT NULL AND lon IS NOT NULL AND path NOT LIKE '%*%'
        AND date(timestamp, '+2 hours') = date('now', '+2 hours')
    """).fetchall()
    db.close()
    return jsonify([[r['lat'], r['lon'], max(0, min(1, (r['rssi']+150)/50))] for r in rows])
@app.route("/api/stations")
def stations_api():
    db = get_db()
    rows = db.execute("""SELECT callsign, first_seen, last_seen, total_packets,
        max_distance, max_distance_date, best_rssi, last_rssi, last_lat, last_lon, last_path
        FROM stations ORDER BY total_packets DESC""").fetchall()
    db.close()
    return jsonify([{"callsign": r["callsign"],
        "first_seen": r["first_seen"][:10] if r["first_seen"] else "-",
        "last_seen": r["last_seen"][:16].replace("T"," ") if r["last_seen"] else "-",
        "total_packets": r["total_packets"],
        "max_distance": round(r["max_distance"],1) if r["max_distance"] else 0,
        "max_distance_date": r["max_distance_date"][:10] if r["max_distance_date"] else "-",
        "best_rssi": r["best_rssi"], "last_rssi": r["last_rssi"],
        "last_path": r["last_path"] or "-"} for r in rows])

@app.route("/api/stations/csv")
def stations_csv():
    import csv, io
    db = get_db()
    rows = db.execute("""SELECT callsign, first_seen, last_seen, total_packets,
        max_distance, max_distance_date, best_rssi, last_rssi, last_lat, last_lon, last_path
        FROM stations ORDER BY total_packets DESC""").fetchall()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Callsign","Prima vista","Ultima vista","Pacchetti totali",
        "Distanza max (km)","Data dist max","RSSI migliore","Ultimo RSSI",
        "Lat","Lon","Ultimo path"])
    for r in rows:
        writer.writerow([
            r["callsign"],
            r["first_seen"][:10] if r["first_seen"] else "",
            r["last_seen"][:16].replace("T"," ") if r["last_seen"] else "",
            r["total_packets"],
            round(r["max_distance"],1) if r["max_distance"] else "",
            r["max_distance_date"][:10] if r["max_distance_date"] else "",
            r["best_rssi"] or "",
            r["last_rssi"] or "",
            round(r["last_lat"],5) if r["last_lat"] else "",
            round(r["last_lon"],5) if r["last_lon"] else "",
            r["last_path"] or ""
        ])
    output.seek(0)
    from flask import Response
    from datetime import datetime
    filename = f"stazioni_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})
@app.route("/api/stations_summary")
def stations_summary():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    best  = db.execute("SELECT callsign, max_distance, max_distance_date FROM stations WHERE max_distance IS NOT NULL ORDER BY max_distance DESC LIMIT 1").fetchone()
    most  = db.execute("SELECT callsign, total_packets FROM stations ORDER BY total_packets DESC LIMIT 1").fetchone()
    db.close()
    return jsonify({"total_stations": total,
        "best_callsign": best["callsign"] if best else "-",
        "best_distance": round(best["max_distance"],1) if best else 0,
        "best_date": best["max_distance_date"][:10] if best and best["max_distance_date"] else "-",
        "most_callsign": most["callsign"] if most else "-",
        "most_packets": most["total_packets"] if most else 0})

@app.route("/api/igate_beacon")
def igate_beacon():
    # Check online via HTTP ping
    try:
        r = req.get(f"http://{IGATE_IP}/", timeout=3)
        online = r.status_code == 200
    except:
        online = False
    db = get_db()
    row = db.execute("SELECT timestamp FROM packets WHERE callsign=? AND msg_type='RX' ORDER BY id DESC LIMIT 1", (CALLSIGN,)).fetchone()
    volt_row = db.execute("SELECT voltage FROM packets WHERE callsign=? AND voltage IS NOT NULL ORDER BY id DESC LIMIT 1", (CALLSIGN,)).fetchone()
    db.close()
    time_str = "-"
    minutes_ago = 999
    if row:
        rt = rome_time(row["timestamp"])
        time_str = rt.strftime("%H:%M") if rt else "-"
        minutes_ago = int((datetime.now(timezone.utc) -
            datetime.strptime(row["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")
            .replace(tzinfo=timezone.utc)).total_seconds() / 60)
    voltage = volt_row["voltage"] if volt_row else None
    return jsonify({"time": time_str, "minutes_ago": minutes_ago,
        "online": online, "voltage": voltage})
@app.route("/api/daily_stats")
def daily_stats_api():
    db = get_db()
    rows = db.execute("""SELECT date, total_packets, total_rf, total_digi,
        unique_stations, best_distance, best_callsign, rssi_avg, crc_errors, peak_hour
        FROM daily_stats ORDER BY date DESC""").fetchall()
    db.close()
    return jsonify([{"date": r["date"], "total_packets": r["total_packets"],
        "total_rf": r["total_rf"], "total_digi": r["total_digi"],
        "unique_stations": r["unique_stations"], "best_distance": r["best_distance"],
        "best_callsign": r["best_callsign"] or "-", "rssi_avg": r["rssi_avg"],
        "crc_errors": r["crc_errors"], "peak_hour": r["peak_hour"] or "-"} for r in rows])

@app.route("/api/services_status")
def services_status():
    services = ["mosquitto", "syslog-collector", "mqtt-telegram", "flask-dashboard",
                "alerts", "cleanup", "meshcom-poller", "meshcom-udp-listener"]
    result = {}
    for name in services:
        try:
            r = subprocess.run(["systemctl", "is-active", name],
                                capture_output=True, text=True)
            result[name] = r.stdout.strip() == "active"
        except Exception:
            result[name] = False
    return jsonify(result)

@app.route("/api/live_temp")
def live_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            millideg = int(f.read().strip())
        return jsonify({"temp": round(millideg / 1000, 1)})
    except Exception as e:
        return jsonify({"temp": None, "error": str(e)})

@app.route("/api/system_stats")
def system_stats_api():
    db = get_db()
    rows = db.execute("""SELECT timestamp, cpu_temp, ram_used, ram_total,
        disk_used, disk_total, uptime_seconds, cpu_perc, cpu_freq, net_rx, net_tx, disk_label
        FROM system_stats ORDER BY id DESC LIMIT 168""").fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({"time": rt.strftime("%d/%m %H:%M") if rt else r["timestamp"][:16],
            "cpu_temp": r["cpu_temp"], "cpu_perc": r["cpu_perc"], "cpu_freq": r["cpu_freq"],
            "ram_used": r["ram_used"], "ram_total": r["ram_total"],
            "ram_perc": round(r["ram_used"]/r["ram_total"]*100,1) if r["ram_total"] else 0,
            "disk_used": r["disk_used"], "disk_total": r["disk_total"],
            "disk_perc": round(r["disk_used"]/r["disk_total"]*100,1) if r["disk_total"] else 0,
            "disk_label": r["disk_label"] or "SD Card",
            "uptime": r["uptime_seconds"], "net_rx": r["net_rx"], "net_tx": r["net_tx"]})
    try:
        live_uptime = int(float(open("/proc/uptime").read().split()[0]))
    except:
        live_uptime = None
    return jsonify({"data": list(reversed(result)), "live_uptime": live_uptime})

@app.route("/api/reboot", methods=["POST"])
def reboot():
    password = request.json.get("password", "")
    target   = request.json.get("target", "server")
    if password != IGATE_REBOOT_PW:
        return jsonify({"ok": False, "msg": "Password errata"})
    if target == "igate":
        try:
            req.post(f"http://{IGATE_IP}/action", data="type=reboot", timeout=5)
            return jsonify({"ok": True, "msg": "iGate riavviato"})
        except Exception as e:
            if any(x in str(e) for x in ["Connection", "reset", "RemoteDisconnected"]):
                return jsonify({"ok": True, "msg": "iGate riavviato"})
            return jsonify({"ok": False, "msg": "iGate non raggiungibile"})
    else:
        subprocess.Popen(["sudo", "reboot"])
        return jsonify({"ok": True, "msg": "Server in riavvio..."})
@app.route("/api/git-update", methods=["POST"])
def git_update():
    password = request.json.get("password", "")
    if password != IGATE_REBOOT_PW:
        return jsonify({"ok": False, "msg": "Password errata"})
    if os.path.exists("/tmp/system-update.running"):
        return jsonify({"ok": False, "msg": "Aggiornamento gia in corso"})
    open("/tmp/system-update.running", "w").close()
    import subprocess as _sp
    script_dir = os.path.expanduser("~/lora-aprs-igate")
    cmd = (
        f"cd {script_dir} && "
        f"bash update.sh >> /tmp/system-update.log 2>&1; "
        "rm -f /tmp/system-update.running; "
        "echo '=== COMPLETATO ===' >> /tmp/system-update.log"
    )
    open("/tmp/system-update.log", "w").close()
    subprocess.Popen(cmd, shell=True)
    return jsonify({"ok": True, "msg": "Aggiornamento da GitHub avviato..."})
@app.route("/api/system-update", methods=["POST"])
def system_update():
    password = request.json.get("password", "")
    if password != IGATE_REBOOT_PW:
        return jsonify({"ok": False, "msg": "Password errata"})
    if os.path.exists("/tmp/system-update.running"):
        return jsonify({"ok": False, "msg": "Aggiornamento gia in corso"})
    open("/tmp/system-update.running", "w").close()
    cmd = (
        "sudo apt update >> /tmp/system-update.log 2>&1 && "
        "sudo apt full-upgrade -y >> /tmp/system-update.log 2>&1; "
        "rm -f /tmp/system-update.running; "
        "echo \'=== COMPLETATO ===\' >> /tmp/system-update.log"
    )
    open("/tmp/system-update.log", "w").close()
    subprocess.Popen(cmd, shell=True)
    return jsonify({"ok": True, "msg": "Aggiornamento avviato in background"})
@app.route("/api/system-update/status")
def system_update_status():
    running = os.path.exists("/tmp/system-update.running")
    log_content = ""
    if os.path.exists("/tmp/system-update.log"):
        with open("/tmp/system-update.log") as f:
            log_content = f.read()[-3000:]
    return jsonify({"running": running, "log": log_content})

@app.route("/settings")
def settings_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/settings.html").read(), callsign=CALLSIGN)

@app.route("/api/settings", methods=["GET"])
def settings_get():
    import importlib.util, types
    cfg_path = "/usr/local/lib/lora-aprs/config.py"
    spec = importlib.util.spec_from_file_location("config", cfg_path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return jsonify({
        "CALLSIGN": getattr(cfg, "CALLSIGN", ""),
        "IGATE_IP": getattr(cfg, "IGATE_IP", ""),
        "IGATE_REBOOT_PW": getattr(cfg, "IGATE_REBOOT_PW", ""),
        "LATITUDE": getattr(cfg, "LATITUDE", 0),
        "LONGITUDE": getattr(cfg, "LONGITUDE", 0),
        "MESHCOM_IP": getattr(cfg, "MESHCOM_IP", ""),
        "HAS_MESHCOM": getattr(cfg, "HAS_MESHCOM", False),
    })

@app.route("/api/settings", methods=["POST"])
def settings_post():
    data = request.json
    pw = data.get("password", "")
    if pw != IGATE_REBOOT_PW:
        return jsonify({"ok": False, "msg": "Password errata"})
    cfg_path = "/usr/local/lib/lora-aprs/config.py"
    with open(cfg_path) as f:
        content = f.read()
    fields = ["CALLSIGN", "IGATE_IP", "LATITUDE", "LONGITUDE", "MESHCOM_IP"]
    for key in fields:
        if key not in data:
            continue
        val = data[key]
        if isinstance(val, str):
            content = __import__("re").sub(
                rf'^{key}\s*=\s*"[^"]*"',
                f'{key}        = "{val}"',
                content, flags=__import__("re").MULTILINE
            )
        else:
            content = __import__("re").sub(
                rf'^{key}\s*=\s*[\d.]+',
                f'{key}        = {val}',
                content, flags=__import__("re").MULTILINE
            )
    with open(cfg_path, "w") as f:
        f.write(content)
    subprocess.Popen(["sudo", "systemctl", "restart", "alerts", "mqtt-telegram", "syslog-collector"])
    def _restart_self():
        subprocess.Popen(["sudo", "systemctl", "restart", "flask-dashboard"])
    threading.Timer(2.0, _restart_self).start()
    return jsonify({"ok": True, "msg": "Impostazioni salvate — servizi in riavvio tra 2s"})
@app.route("/battery")
def battery_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/battery.html").read(), callsign=CALLSIGN)
@app.route("/crc")
def crc_page():
    return render_template_string(open(f"{DASHBOARD_DIR}/crc.html").read(), callsign=CALLSIGN)
@app.route("/api/crc")
def crc_api():
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, rssi, snr, raw FROM packets
        WHERE msg_type='CRC'
        AND replace(timestamp,'T',' ') >= datetime('now', '-24 hours')
        ORDER BY id DESC LIMIT 200
    """).fetchall()
    db.close()
    return jsonify([{"time": rome_time(r["timestamp"]).strftime("%d/%m %H:%M:%S") if rome_time(r["timestamp"]) else r["timestamp"][:19],
        "rssi": r["rssi"], "snr": r["snr"], "raw": r["raw"]} for r in rows])
@app.route("/api/events")
def events_api():
    db = get_db()
    rows = db.execute("SELECT id, timestamp, type, message FROM events ORDER BY id DESC LIMIT 100").fetchall()
    db.close()
    return jsonify([{"id": r["id"],
        "time": rome_time(r["timestamp"]).strftime("%d/%m %H:%M") if rome_time(r["timestamp"]) else r["timestamp"][:16],
        "type": r["type"], "message": r["message"]} for r in rows])

@app.route("/api/reboot_igate", methods=["POST"])
def reboot_igate_direct():
    try:
        r = req.post(f"http://{IGATE_IP}/action", data="type=reboot", timeout=10)
        return jsonify({"ok": True, "msg": "iGate riavviato"})
    except Exception as e:
        if any(x in str(e) for x in ["Connection", "reset", "RemoteDisconnected"]):
            return jsonify({"ok": True, "msg": "iGate riavviato"})
        return jsonify({"ok": False, "msg": str(e)})

@app.route("/configuration.json", methods=["GET", "POST"])
def igate_config_json_root():
    try:
        if request.method == "POST":
            r = req.post(f"http://{IGATE_IP}/configuration.json",
                        data=request.get_data(),
                        headers={"Content-Type": request.content_type},
                        timeout=10)
        else:
            r = req.get(f"http://{IGATE_IP}/configuration.json", timeout=10)
        return r.content, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")}
    except Exception as e:
        return jsonify({"error": str(e)}), 503

@app.route("/received-packets.json", methods=["GET"])
def igate_packets_json_root():
    try:
        r = req.get(f"http://{IGATE_IP}/received-packets.json", timeout=10)
        return r.content, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")}
    except Exception as e:
        return jsonify({"error": str(e)}), 503

@app.route("/igate/configuration.json", methods=["GET", "POST"])
def igate_config_json():
    try:
        if request.method == "POST":
            r = req.post(f"http://{IGATE_IP}/configuration.json", 
                        data=request.get_data(),
                        headers={"Content-Type": request.content_type},
                        timeout=10)
        else:
            r = req.get(f"http://{IGATE_IP}/configuration.json", timeout=10)
        return r.content, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")}
    except Exception as e:
        return jsonify({"error": str(e)}), 503

@app.route("/igate")
@app.route("/igate/<path:subpath>", methods=["GET", "POST"])
def igate_proxy(subpath=""):
    try:
        url = f"http://{IGATE_IP}/{subpath}"
        if request.method == "POST":
            r = req.post(url, data=request.get_data(), headers={"Content-Type": request.content_type}, timeout=10)
        else:
            r = req.get(url, params=request.args, timeout=10)
        
        # Riscrive i link relativi per passare attraverso il proxy
        content_type = r.headers.get("Content-Type", "")
        if "text/html" in content_type:
            body = r.content
            try:
                import gzip
                body = gzip.decompress(body)
            except:
                pass
            body = body.decode("utf-8", errors="ignore")
            body = body.replace('href="/', 'href="/igate/')
            body = body.replace('src="/', 'src="/igate/')
            body = body.replace('action="/', 'action="/igate/')
            body = body.replace("fetch('/", "fetch('/igate/")
            body = body.replace('fetch("/', 'fetch("/igate/')
            body = body.replace("url: '/", "url: '/igate/")
            body = body.replace('url: "/', 'url: "/igate/')
            body = body.replace("XMLHttpRequest", "XMLHttpRequest")
            body = body.replace("'/configuration.json'", "'/igate/configuration.json'")
            body = body.replace('"/configuration.json"', '"/igate/configuration.json"')
            body = body.replace("'/action'", "'/igate/action'")
            body = body.replace('"/action"', '"/igate/action"')
            return body, r.status_code, {"Content-Type": "text/html"}
        
        if "javascript" in content_type or subpath.endswith(".js"):
            body = r.content
            try:
                import gzip
                body = gzip.decompress(body)
            except:
                pass
            body = body.decode("utf-8", errors="ignore")
            return body, r.status_code, {"Content-Type": "application/javascript"}
        return r.content, r.status_code, {"Content-Type": content_type}
    except Exception as e:
        return f"<h1>iGate non raggiungibile</h1><p>{e}</p>", 503


# ─── MeshCom IU5MGF-12 ───────────────────────────────────────────────────────

@app.route("/meshcom")
def meshcom_page():
    if not HAS_MESHCOM:
        return "MeshCom non configurato", 404
    return render_template_string(open(f"{DASHBOARD_DIR}/meshcom.html").read())

@app.route("/api/meshcom/status")
def meshcom_status():
    if not HAS_MESHCOM:
        return jsonify({"enabled": False})
    db = get_db()
    row = db.execute("SELECT * FROM meshcom_status ORDER BY id DESC LIMIT 1").fetchone()
    db.close()
    if not row:
        return jsonify({})
    rt = rome_time(row["timestamp"])
    minutes_ago = int((datetime.now(timezone.utc) -
        datetime.strptime(row["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")
        .replace(tzinfo=timezone.utc)).total_seconds() / 60)
    return jsonify({
        "callsign":    row["callsign"],
        "firmware":    row["firmware"],
        "battery_v":   row["battery_v"],
        "battery_pct": row["battery_pct"],
        "wifi_rssi":   row["wifi_rssi"],
        "gateway_on":  row["gateway_on"],
        "uptime_start": row["uptime_start"],
        "last_seen":   rt.strftime("%H:%M:%S") if rt else "-",
        "minutes_ago": minutes_ago,
        "online":      minutes_ago < 3,
    })

@app.route("/api/meshcom/messages")
def meshcom_messages():
    if not HAS_MESHCOM:
        return jsonify([])
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, callsign, dest, message
        FROM meshcom_messages
        ORDER BY id DESC LIMIT 200
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({
            "time": rt.strftime("%d/%m %H:%M:%S") if rt else r["timestamp"][:19],
            "callsign": r["callsign"],
            "dest": r["dest"],
            "message": r["message"]
        })
    return jsonify(result)
@app.route("/api/meshcom/mheard")
def meshcom_mheard():
    db = get_db()
    rows = db.execute("""
        SELECT m.* FROM meshcom_mheard m
        INNER JOIN (
            SELECT callsign, MAX(id) as max_id FROM meshcom_mheard GROUP BY callsign
        ) latest ON m.id = latest.max_id
        ORDER BY m.timestamp DESC
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({
            "callsign": r["callsign"],
            "rssi":     r["rssi"],
            "snr":      r["snr"],
            "distance": r["distance"],
            "lat":      r["lat"],
            "lon":      r["lon"],
            "alt":      r["alt"],
            "hardware": r["hardware"],
            "msg_type": r["msg_type"],
            "last_seen": rt.strftime("%d/%m %H:%M:%S") if rt else "-",
        })
    return jsonify(result)

@app.route("/api/meshcom/rxlog")
def meshcom_rxlog():
    db = get_db()
    rows = db.execute(
        "SELECT timestamp, src_call, dst_call, path, rssi, snr, raw "
        "FROM meshcom_rxlog ORDER BY id DESC LIMIT 100"
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({
            "time":     rt.strftime("%d/%m %H:%M:%S") if rt else r["timestamp"][11:19],
            "src_call": r["src_call"],
            "dst_call": r["dst_call"],
            "path":     r["path"],
            "rssi":     r["rssi"],
            "snr":      r["snr"],
            "raw":      r["raw"],
        })
    return jsonify(result)

@app.route("/wx")
def wx_page():
    if not HAS_MESHCOM:
        return "MeshCom non configurato", 404
    return render_template_string(open(f"{DASHBOARD_DIR}/wx.html").read())

@app.route("/api/meshcom/weather")
def meshcom_weather():
    if not HAS_MESHCOM:
        return jsonify({"enabled": False})
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, callsign, temp, hum, qfe, qnh, gas
        FROM meshcom_weather ORDER BY id DESC LIMIT 288
    """).fetchall()
    db.close()
    result = []
    for r in rows:
        rt = rome_time(r["timestamp"])
        result.append({
            "time": rt.strftime("%d/%m %H:%M") if rt else r["timestamp"][:16],
            "callsign": r["callsign"],
            "temp": r["temp"],
            "hum": r["hum"],
            "qfe": r["qfe"],
            "qnh": r["qnh"],
            "gas": r["gas"],
        })
    return jsonify(list(reversed(result)))

@app.route("/api/meshcom/weather_latest")
def meshcom_weather_latest():
    if not HAS_MESHCOM:
        return jsonify({"enabled": False})
    db = get_db()
    row = db.execute("""
        SELECT timestamp, callsign, temp, hum, qfe, qnh, gas
        FROM meshcom_weather ORDER BY id DESC LIMIT 1
    """).fetchone()
    db.close()
    if not row:
        return jsonify({})
    rt = rome_time(row["timestamp"])
    return jsonify({
        "time": rt.strftime("%H:%M") if rt else "-",
        "callsign": row["callsign"],
        "temp": row["temp"],
        "hum": row["hum"],
        "qfe": row["qfe"],
        "qnh": row["qnh"],
        "gas": row["gas"],
    })

@app.route("/api/meshcom/rssi_history")
def meshcom_rssi_history():
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, callsign, rssi, snr FROM meshcom_mheard
        WHERE rssi IS NOT NULL ORDER BY id DESC LIMIT 200
    """).fetchall()
    db.close()
    result = {}
    for r in rows:
        call = r["callsign"]
        if call not in result:
            result[call] = []
        rt = rome_time(r["timestamp"])
        result[call].append({"time": rt.strftime("%H:%M") if rt else "-", "rssi": r["rssi"], "snr": r["snr"]})
    for call in result:
        result[call] = list(reversed(result[call]))
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
