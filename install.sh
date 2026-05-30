#!/bin/bash
# ============================================
# LoRa APRS iGate - Script di installazione
# CA2RXU + RPi + Dashboard Web + Telegram
# ============================================

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "================================================"
echo "  LoRa APRS iGate - Installazione automatica"
echo "  CA2RXU + RPi + Dashboard Web + Telegram"
echo "================================================"
echo -e "${NC}"

echo -e "${YELLOW}Inserisci i dati di configurazione:${NC}"
echo ""

read -p "Callsign iGate (es. IU5PSY-10): " CALLSIGN
CALLSIGN_BASE=$(echo $CALLSIGN | cut -d'-' -f1)
read -p "Passcode APRS-IS: " PASSCODE
read -p "Latitudine (es. 43.5632): " LAT
read -p "Longitudine (es. 11.5375): " LON
read -p "Token bot Telegram notifiche: " BOT_TOKEN
read -p "Token bot Telegram alert: " ALERT_TOKEN
read -p "Chat ID Telegram: " CHAT_ID
read -p "Password reboot dashboard (default: raspberry): " REBOOT_PWD
REBOOT_PWD=${REBOOT_PWD:-raspberry}
read -p "IP iGate CA2RXU (default: 192.168.2.10): " IGATE_IP
IGATE_IP=${IGATE_IP:-192.168.2.10}
read -p "OLED SSD1306 collegato? (si/no): " HAS_OLED
read -p "SSD esterno montato? (si/no): " HAS_SSD
read -p "Nome utente RPi (default: pi): " RPI_USER
RPI_USER=${RPI_USER:-pi}

if [ "$HAS_SSD" = "si" ]; then
    DATA_PATH="/mnt/ssd/radio"
else
    DATA_PATH="/home/${RPI_USER}/radio"
fi

echo ""
echo -e "${YELLOW}Riepilogo:${NC}"
echo "  Callsign:  $CALLSIGN"
echo "  Posizione: $LAT, $LON"
echo "  iGate IP:  $IGATE_IP"
echo "  Storage:   $DATA_PATH"
echo "  OLED:      $HAS_OLED"
echo ""
read -p "Confermi? (si/no): " CONFIRM
if [ "$CONFIRM" != "si" ]; then
    echo "Installazione annullata."
    exit 1
fi

# ============================================
# INSTALLAZIONE PACCHETTI
# ============================================
echo -e "${CYAN}[1/6] Aggiornamento sistema...${NC}"
sudo apt-get update -q
sudo apt-get upgrade -y -q

echo -e "${CYAN}[2/6] Installazione pacchetti...${NC}"
sudo apt-get install -y -q \
    python3 python3-pip \
    mosquitto mosquitto-clients \
    sqlite3 curl wget git

echo -e "${CYAN}[3/6] Installazione librerie Python...${NC}"
sudo pip3 install --break-system-packages \
    flask pytz requests

if [ "$HAS_OLED" = "si" ]; then
    sudo pip3 install --break-system-packages \
        luma.oled luma.core pillow
    sudo raspi-config nonint do_i2c 0
    echo -e "${GREEN}I2C abilitato${NC}"
fi

sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# ============================================
# STRUTTURA CARTELLE E DATABASE
# ============================================
echo -e "${CYAN}[4/6] Creazione struttura...${NC}"

sudo mkdir -p ${DATA_PATH}/data
sudo mkdir -p ${DATA_PATH}/flask-dashboard
sudo mkdir -p ${DATA_PATH}/backup
sudo chown -R ${RPI_USER}:${RPI_USER} ${DATA_PATH}

if [ "$HAS_SSD" = "si" ]; then
    sudo mkdir -p /mnt/ssd/oled
    sudo chown -R ${RPI_USER}:${RPI_USER} /mnt/ssd/oled
fi

sqlite3 ${DATA_PATH}/data/aprs.db "
CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, msg_type TEXT, callsign TEXT, path TEXT,
    crc_ok INTEGER, rssi REAL, snr REAL, freq_err REAL,
    distance REAL, lat REAL, lon REAL, comment TEXT, raw TEXT, voltage REAL
);
CREATE TABLE IF NOT EXISTS stations (
    callsign TEXT PRIMARY KEY,
    first_seen TEXT, last_seen TEXT, total_packets INTEGER DEFAULT 0,
    max_distance REAL, max_distance_date TEXT,
    best_rssi REAL, last_rssi REAL, last_lat REAL, last_lon REAL, last_path TEXT
);
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY, total_packets INTEGER, total_rf INTEGER,
    total_digi INTEGER, unique_stations INTEGER, best_distance REAL,
    best_callsign TEXT, rssi_avg REAL, crc_errors INTEGER, peak_hour TEXT
);
CREATE TABLE IF NOT EXISTS system_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
    cpu_temp REAL, ram_used INTEGER, ram_total INTEGER,
    disk_used INTEGER, disk_total INTEGER, uptime_seconds INTEGER,
    cpu_perc REAL, cpu_freq INTEGER, net_rx INTEGER, net_tx INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, type TEXT, message TEXT
);
"

echo "0" > ${DATA_PATH}/data/last_notified_id
echo '{"silence":false,"igate_offline":false,"battery_low":false,"containers":{}}' > ${DATA_PATH}/data/alert_state.json
echo -e "${GREEN}Struttura creata${NC}"

# ============================================
# DOWNLOAD FILE DA GITHUB
# ============================================
echo -e "${CYAN}[5/6] Download file da GitHub...${NC}"

REPO="https://raw.githubusercontent.com/IU5MGF/lora-aprs-igate/main"
SCRIPTS_DIR="/usr/local/bin"
DASHBOARD_DIR="${DATA_PATH}/flask-dashboard"

# funzione download e sostituzione variabili
install_file() {
    local src=$1
    local dst=$2
    curl -sSL "${REPO}/${src}" -o "${dst}"
    sed -i "s/CALLSIGN_PLACEHOLDER/${CALLSIGN}/g" "${dst}"
    sed -i "s/BOT_TOKEN_PLACEHOLDER/${BOT_TOKEN}/g" "${dst}"
    sed -i "s/ALERT_TOKEN_PLACEHOLDER/${ALERT_TOKEN}/g" "${dst}"
    sed -i "s/CHAT_ID_PLACEHOLDER/${CHAT_ID}/g" "${dst}"
    sed -i "s/IGATE_IP_PLACEHOLDER/${IGATE_IP}/g" "${dst}"
    sed -i "s/REBOOT_PWD_PLACEHOLDER/${REBOOT_PWD}/g" "${dst}"
    sed -i "s|DATA_PATH_PLACEHOLDER|${DATA_PATH}|g" "${dst}"
    sed -i "s/RPI_USER_PLACEHOLDER/${RPI_USER}/g" "${dst}"
    sed -i "s/LOCATION_PLACEHOLDER/${CALLSIGN_BASE}/g" "${dst}"
}

# script Python
for script in syslog-collector.py mqtt-telegram.py alerts.py cleanup.py daily-stats.py system-stats.py; do
    install_file "scripts/${script}" "${SCRIPTS_DIR}/${script}"
    chmod +x "${SCRIPTS_DIR}/${script}"
    echo -e "  ${GREEN}✓ ${script}${NC}"
done

# mqtt-watchdog
install_file "scripts/mqtt-watchdog.sh" "${SCRIPTS_DIR}/mqtt-watchdog.sh"
chmod +x "${SCRIPTS_DIR}/mqtt-watchdog.sh"

# flask-dashboard
install_file "scripts/flask-dashboard.py" "${SCRIPTS_DIR}/flask-dashboard.py"
chmod +x "${SCRIPTS_DIR}/flask-dashboard.py"

# file HTML dashboard
for f in index.html map.html stations.html stats.html server.html events.html dashboard.js; do
    install_file "dashboard/${f}" "${DASHBOARD_DIR}/${f}"
    echo -e "  ${GREEN}✓ ${f}${NC}"
done

# oled (solo se presente)
if [ "$HAS_OLED" = "si" ]; then
    if [ "$HAS_SSD" = "si" ]; then
        OLED_PATH="/mnt/ssd/oled/oled.py"
    else
        OLED_PATH="/home/${RPI_USER}/oled/oled.py"
        mkdir -p /home/${RPI_USER}/oled
    fi
    install_file "oled/oled.py" "${OLED_PATH}"
    chmod +x "${OLED_PATH}"
    echo -e "  ${GREEN}✓ oled.py${NC}"
fi

# servizi systemd
for svc in syslog-collector mqtt-telegram alerts cleanup flask-dashboard; do
    install_file "services/${svc}.service" "/etc/systemd/system/${svc}.service"
done

if [ "$HAS_OLED" = "si" ]; then
    install_file "services/oled.service" "/etc/systemd/system/oled.service"
    # aggiorna path oled nel service
    sudo sed -i "s|/mnt/ssd/oled/oled.py|${OLED_PATH}|g" /etc/systemd/system/oled.service
fi

echo -e "${GREEN}File installati${NC}"

# ============================================
# AVVIO SERVIZI E CRON
# ============================================
echo -e "${CYAN}[6/6] Avvio servizi...${NC}"

sudo systemctl daemon-reload
sudo systemctl enable mosquitto syslog-collector mqtt-telegram alerts cleanup flask-dashboard
sudo systemctl start mosquitto syslog-collector mqtt-telegram alerts cleanup flask-dashboard

if [ "$HAS_OLED" = "si" ]; then
    sudo systemctl enable oled
    sudo systemctl start oled
fi

# cron
(crontab -l 2>/dev/null; cat << CRONEOF
*/10 * * * * /usr/local/bin/mqtt-watchdog.sh
30 3 * * * curl -s "http://${IGATE_IP}/action?type=reboot" > /dev/null 2>&1
35 3 * * * sudo reboot
1 0 * * * /usr/bin/python3 /usr/local/bin/daily-stats.py >> ${DATA_PATH}/data/daily-stats.log 2>&1
0 3 * * * /usr/bin/python3 /usr/local/bin/daily-stats.py >> ${DATA_PATH}/data/daily-stats.log 2>&1
*/15 * * * * /usr/bin/python3 /usr/local/bin/system-stats.py >> ${DATA_PATH}/data/system-stats.log 2>&1
CRONEOF
) | crontab -

echo -e "${GREEN}Cron configurato${NC}"

# ============================================
# VERIFICA FINALE
# ============================================
sleep 5
echo ""
echo -e "${CYAN}Verifica servizi:${NC}"
ALL_OK=true
SERVICES="mosquitto syslog-collector mqtt-telegram alerts cleanup flask-dashboard"
if [ "$HAS_OLED" = "si" ]; then SERVICES="$SERVICES oled"; fi

for svc in $SERVICES; do
    STATUS=$(systemctl is-active $svc)
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}✓ $svc${NC}"
    else
        echo -e "  ${RED}✗ $svc${NC}"
        ALL_OK=false
    fi
done

echo ""
IP=$(hostname -I | awk '{print $1}')
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}  Installazione completata con successo!${NC}"
    echo -e "${GREEN}================================================${NC}"
else
    echo -e "${YELLOW}  Installazione completata con avvisi${NC}"
    echo -e "${YELLOW}  Verifica i servizi in rosso${NC}"
fi

echo ""
echo -e "${CYAN}Dashboard:${NC} http://${IP}:5000"
echo -e "${CYAN}Callsign:${NC}  ${CALLSIGN}"
echo ""
echo -e "${YELLOW}Prossimi passi:${NC}"
echo "  1. Configura CA2RXU su http://${IGATE_IP}"
echo "  2. Imposta syslog verso ${IP}:1514"
echo "  3. Verifica: journalctl -u syslog-collector -f"
echo ""
