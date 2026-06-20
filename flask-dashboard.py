from flask import Flask, jsonify, render_template_string, request
import sqlite3
import subprocess
import requests as req
from datetime import datetime, timezone
import os
import sys
import pytz

sys.path.insert(0, "/usr/local/lib/lora-aprs")
from config import (
    CALLSIGN, DB_PATH, TIMEZONE, DATA_DIR,
    IGATE_IP, IGATE_REBOOT_PW, HAS_SSD, SSD_MOUNT
)
try:
    from config import HAS_MESHCOM, MESHCOM_CALLSIGN
except ImportError:
    HAS_MESHCOM = False
    MESHCOM_CALLSIGN = ""

DASHBOARD_DIR = os.path.join(os.path.dirname(DATA_DIR), "flask-dashboard")

app = Flask(__name__, static_folder=DASHBOARD_DIR, static_url_path="/static")
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
    return render_template_string(open(f"{DASHBOARD_DIR}/map.html").read(), callsign=CALLSIGN)

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
    db.close()
    return jsonify({"total": total, "unique": unique,
        "best_callsign": best[0] if best else "-",
        "best_distance": best[1] if best else 0,
        "rssi_avg": round(rssi_avg, 1) if rssi_avg else 0,
        "crc_errors": crc_errors})

@app.route("/api/packets")
def packets():
    db = get_db()
    rows = db.execute("""
        SELECT timestamp, callsign, path, rssi, snr, distance, comment FROM
        (SELECT timestamp, callsign, path, rssi, snr, distance, comment, id FROM packets
         WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ?
         AND path != 'MESHCOM' ORDER BY id DESC LIMIT 40)
        UNION ALL
        SELECT timestamp, callsign, path, rssi, snr, distance, comment FROM
        (SELECT timestamp, callsign, path, rssi, snr, distance, comment, id FROM packets
         WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != ?
         AND path = 'MESHCOM' ORDER BY id DESC LIMIT 10)
    """, (CALLSIGN, CALLSIGN)).fetchall()
    rows = sorted(rows, key=lambda r: r["timestamp"], reverse=True)[:50]
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
        own_callsigns.append(MESHCOM_CALLSIGN)
    except: pass
    rows = db.execute("""
        SELECT callsign, lat, lon, rssi, distance, timestamp, path
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
        SELECT callsign, lat, lon, rssi, distance, timestamp, path
        FROM packets WHERE callsign IN ({})
        AND lat IS NOT NULL AND lon IS NOT NULL
        AND id IN (SELECT MAX(id) FROM packets WHERE callsign IN ({}) GROUP BY callsign)
    """.format(','.join('?'*len(own_callsigns)), ','.join('?'*len(own_callsigns))),
        own_callsigns + own_callsigns).fetchall()
    db.close()
    result = [{"callsign": r["callsign"], "lat": r["lat"], "lon": r["lon"],
        "rssi": r["rssi"], "distance": r["distance"],
        "type": 'meshcom' if r['path'] == 'MESHCOM' else ('digi' if r['path'] and '*' in r['path'] else 'rf'),
        "last_ts": r["timestamp"]} for r in rows]
    for r in own_rows:
        result.append({"callsign": r["callsign"], "lat": r["lat"], "lon": r["lon"],
            "rssi": r["rssi"], "distance": r["distance"],
            "type": "own", "last_ts": r["timestamp"]})
    return jsonify(result)

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
            SELECT lat, lon, rssi, timestamp, path FROM packets
            WHERE crc_ok=1 AND msg_type='RX' AND callsign=?
            AND lat IS NOT NULL AND lon IS NOT NULL
            AND replace(timestamp,'T',' ') >= datetime('now', '-' || ? || ' minutes')
            ORDER BY timestamp ASC
        """, (call, minutes)).fetchall()
        if not points:
            continue
        last_path = points[-1]['path'] or ''
        result[call] = {
            'type': 'digi' if '*' in last_path else 'rf',
            'points': [{'lat': p['lat'], 'lon': p['lon'], 'rssi': p['rssi'],
                'time': rome_time(p['timestamp']).strftime('%H:%M') if rome_time(p['timestamp']) else '-'}
                for p in points]}
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
    db = get_db()
    row = db.execute("SELECT timestamp FROM packets WHERE callsign=? AND msg_type='RX' ORDER BY id DESC LIMIT 1", (CALLSIGN,)).fetchone()
    db.close()
    if row:
        rt = rome_time(row["timestamp"])
        minutes_ago = int((datetime.now(timezone.utc) -
            datetime.strptime(row["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")
            .replace(tzinfo=timezone.utc)).total_seconds() / 60)
        return jsonify({"time": rt.strftime("%H:%M") if rt else "-",
            "minutes_ago": minutes_ago, "online": minutes_ago < 15})
    return jsonify({"time": "-", "minutes_ago": 999, "online": False})
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

@app.route("/api/system_stats")
def system_stats_api():
    db = get_db()
    rows = db.execute("""SELECT timestamp, cpu_temp, ram_used, ram_total,
        disk_used, disk_total, uptime_seconds, cpu_perc, cpu_freq, net_rx, net_tx
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
        "online":      minutes_ago < 5,
    })

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
            "last_seen": rt.strftime("%H:%M:%S") if rt else "-",
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
            "time":     rt.strftime("%H:%M:%S") if rt else r["timestamp"][11:19],
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
