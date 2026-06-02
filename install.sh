#!/bin/bash
# =============================================================================
# install.sh — Installer interattivo LoRa APRS iGate
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "============================================="
echo "   LoRa APRS iGate — Installer interattivo"
echo "============================================="
echo -e "${NC}"

ask() {
    local prompt="$1"
    local default="$2"
    local var
    if [ -n "$default" ]; then
        read -p "$(echo -e ${YELLOW})${prompt} [${default}]: $(echo -e ${NC})" var
        echo "${var:-$default}"
    else
        read -p "$(echo -e ${YELLOW})${prompt}: $(echo -e ${NC})" var
        echo "$var"
    fi
}

ask_yn() {
    local prompt="$1"
    local default="$2"
    local var
    while true; do
        read -p "$(echo -e ${YELLOW})${prompt} [s/n, default: ${default}]: $(echo -e ${NC})" var
        var="${var:-$default}"
        case "$var" in
            s|S|y|Y) echo "True"; return ;;
            n|N)     echo "False"; return ;;
            *) echo -e "${RED}Risposta non valida, usa s o n${NC}" ;;
        esac
    done
}

echo -e "${CYAN}--- Configurazione iGate ---${NC}"
CALLSIGN=$(ask "Callsign iGate (es. IZ5XXX-10)")
IGATE_IP=$(ask "IP locale iGate" "192.168.2.10")
IGATE_REBOOT_PW=$(ask "Password reboot iGate" "raspberry")

echo ""
echo -e "${CYAN}--- Telegram notifiche pacchetti ---${NC}"
BOT_TOKEN_NOTIFY=$(ask "Bot Token Telegram (notifiche)")
CHAT_ID_NOTIFY=$(ask "Chat ID Telegram (notifiche)")

echo ""
echo -e "${CYAN}--- Telegram alert sistema ---${NC}"
SAME_BOT=$(ask_yn "Usare lo stesso bot anche per gli alert?" "s")
if [ "$SAME_BOT" = "True" ]; then
    BOT_TOKEN_ALERT="$BOT_TOKEN_NOTIFY"
    CHAT_ID_ALERT="$CHAT_ID_NOTIFY"
else
    BOT_TOKEN_ALERT=$(ask "Bot Token Telegram (alert)")
    CHAT_ID_ALERT=$(ask "Chat ID Telegram (alert)")
fi

echo ""
echo -e "${CYAN}--- Posizione iGate ---${NC}"
LATITUDE=$(ask "Latitudine decimale (es. 43.68047)")
LONGITUDE=$(ask "Longitudine decimale (es. 11.52987)")

# Geocoding inverso
echo ""
echo -e "${GREEN}Ricerca citta dalle coordinate...${NC}"
LOCATION=$(curl -s --max-time 5 "https://nominatim.openstreetmap.org/reverse?lat=${LATITUDE}&lon=${LONGITUDE}&format=json" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['address'].get('city') or d['address'].get('town') or d['address'].get('village',''))" 2>/dev/null)
if [ -z "$LOCATION" ]; then
    echo -e "${YELLOW}  Geocoding non disponibile${NC}"
    LOCATION=$(ask "Inserisci la tua citta")
else
    echo -e "${GREEN}  Citta trovata: ${LOCATION}${NC}"
    read -p "$(echo -e ${YELLOW})Confermi ${LOCATION}? [s/n, default: s]: $(echo -e ${NC})" confirm
    confirm="${confirm:-s}"
    if [ "$confirm" != "s" ] && [ "$confirm" != "S" ]; then
        LOCATION=$(ask "Inserisci la tua citta")
    fi
fi

echo ""
echo -e "${CYAN}--- Storage ---${NC}"
HAS_SSD=$(ask_yn "SSD presente?" "s")
if [ "$HAS_SSD" = "True" ]; then
    SSD_MOUNT=$(ask "Path mount SSD" "/mnt/ssd")
    DATA_DIR="${SSD_MOUNT}/radio/data"
else
    SSD_MOUNT=""
    DATA_DIR="/home/pi/radio/data"
fi

echo ""
echo -e "${CYAN}--- Hardware opzionale ---${NC}"
HAS_OLED=$(ask_yn "OLED SSD1306 presente?" "n")
if [ "$HAS_OLED" = "True" ]; then
    OLED_I2C_ADDR=$(ask "Indirizzo I2C OLED (hex)" "0x3C")
else
    OLED_I2C_ADDR="0x3C"
fi

echo ""
echo -e "${CYAN}--- Database ---${NC}"
DB_RETENTION=$(ask "Retention pacchetti (giorni)" "30")

echo ""
echo -e "${CYAN}--- Timezone ---${NC}"
TIMEZONE=$(ask "Timezone" "Europe/Rome")

# =============================================================================
# Genera config.py
# =============================================================================
echo ""
echo -e "${GREEN}Generazione config.py...${NC}"

CONFIG_PATH="/usr/local/lib/lora-aprs/config.py"
sudo mkdir -p "$(dirname $CONFIG_PATH)"

sudo tee "$CONFIG_PATH" > /dev/null << CONFEOF
# =============================================================================
# config.py — Generato da install.sh il $(date '+%Y-%m-%d %H:%M')
# =============================================================================

CALLSIGN        = "${CALLSIGN}"
IGATE_IP        = "${IGATE_IP}"
IGATE_REBOOT_PW = "${IGATE_REBOOT_PW}"

BOT_TOKEN_NOTIFY = "${BOT_TOKEN_NOTIFY}"
CHAT_ID_NOTIFY   = "${CHAT_ID_NOTIFY}"

BOT_TOKEN_ALERT  = "${BOT_TOKEN_ALERT}"
CHAT_ID_ALERT    = "${CHAT_ID_ALERT}"

LATITUDE        = ${LATITUDE}
LONGITUDE       = ${LONGITUDE}

HAS_SSD         = ${HAS_SSD}
SSD_MOUNT       = "${SSD_MOUNT}"
DATA_DIR        = "${DATA_DIR}"
DB_PATH         = "${DATA_DIR}/aprs.db"

HAS_OLED        = ${HAS_OLED}
OLED_I2C_ADDR   = ${OLED_I2C_ADDR}

DB_RETENTION_DAYS = ${DB_RETENTION}

TIMEZONE        = "${TIMEZONE}"

MQTT_HOST       = "localhost"
MQTT_PORT       = 1883
CONFEOF

echo -e "${GREEN}config.py scritto in ${CONFIG_PATH}${NC}"

# =============================================================================
# Installa dipendenze Python
# =============================================================================
echo ""
echo -e "${GREEN}Installazione dipendenze Python...${NC}"
sudo pip3 install paho-mqtt requests pytz flask --break-system-packages

if [ "$HAS_OLED" = "True" ]; then
    sudo pip3 install luma.oled pillow --break-system-packages
fi

# =============================================================================
# Crea directory dati
# =============================================================================
echo ""
echo -e "${GREEN}Creazione directory dati in ${DATA_DIR}...${NC}"
sudo mkdir -p "$DATA_DIR"
sudo mkdir -p "$DATA_DIR"
    sudo chown -R $(logname):$(logname) "$DATA_DIR" 2>/dev/null || true
    sudo chmod 755 "$DATA_DIR"

# =============================================================================
# Copia script
# =============================================================================
echo ""
echo -e "${GREEN}Copia script in /usr/local/bin/...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)/scripts"
SCRIPTS="mqtt-telegram.py alerts.py cleanup.py system-stats.py daily-stats.py syslog-collector.py mqtt-watchdog.sh flask-dashboard.py"
for s in $SCRIPTS; do
    if [ -f "$SCRIPT_DIR/$s" ]; then
        sudo cp "$SCRIPT_DIR/$s" "/usr/local/bin/$s"
        sudo chmod +x "/usr/local/bin/$s"
        echo "  ✓ $s"
    else
        echo -e "  ${RED}✗ $s non trovato in $SCRIPT_DIR${NC}"
    fi
done

if [ "$HAS_OLED" = "True" ]; then
    sudo mkdir -p "${SSD_MOUNT}/oled"
    if [ -f "$SCRIPT_DIR/oled.py" ]; then
        sudo cp "$SCRIPT_DIR/oled.py" "${SSD_MOUNT}/oled/oled.py"
        echo "  ✓ oled.py"
    fi
fi

# =============================================================================
# Installa servizi systemd
# =============================================================================
echo ""
echo -e "${GREEN}Installazione servizi systemd...${NC}"

install_service() {
    local name="$1"
    local desc="$2"
    local exec="$3"
    sudo tee "/etc/systemd/system/${name}.service" > /dev/null << SVCEOF
[Unit]
Description=${desc}
After=network.target

[Service]
ExecStart=${exec}
User=$(logname)
Environment=PYTHONPATH=/usr/local/lib/lora-aprs
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF
    sudo systemctl enable "$name" 2>/dev/null
    sudo systemctl restart "$name" 2>/dev/null || true
    echo "  ✓ ${name}.service"
}

install_service "syslog-collector" "LoRa APRS Syslog Collector"   "/usr/bin/python3 /usr/local/bin/syslog-collector.py"
install_service "mqtt-telegram"    "LoRa APRS MQTT Telegram"      "/usr/bin/python3 /usr/local/bin/mqtt-telegram.py"
install_service "alerts"           "LoRa APRS Alerts"             "/usr/bin/python3 /usr/local/bin/alerts.py"
install_service "cleanup"          "LoRa APRS DB Cleanup"         "/usr/bin/python3 /usr/local/bin/cleanup.py"
install_service "flask-dashboard"  "LoRa APRS Flask Dashboard"    "/usr/bin/python3 /usr/local/bin/flask-dashboard.py"

if [ "$HAS_OLED" = "True" ]; then
    install_service "oled" "LoRa APRS OLED Display" "/usr/bin/python3 ${SSD_MOUNT}/oled/oled.py"
fi

sudo systemctl daemon-reload

# =============================================================================
# Crontab
# =============================================================================
echo ""
echo -e "${GREEN}Configurazione crontab...${NC}"

(crontab -l 2>/dev/null | grep -v "lora-aprs\|mqtt-watchdog\|daily-stats\|system-stats\|backup\|reboot iGate"; cat << CRONEOF
# lora-aprs
0 2 * * * /bin/bash ${DATA_DIR}/../backup.sh
*/10 * * * * /usr/local/bin/mqtt-watchdog.sh
30 3 * * * curl -s -X POST "http://${IGATE_IP}/action?type=reboot"
35 3 * * * sudo reboot
1 0 * * * /usr/bin/python3 /usr/local/bin/daily-stats.py >> ${DATA_DIR}/daily-stats.log 2>&1
0 3 * * * /usr/bin/python3 /usr/local/bin/daily-stats.py >> ${DATA_DIR}/daily-stats.log 2>&1
*/15 * * * * /usr/bin/python3 /usr/local/bin/system-stats.py >> ${DATA_DIR}/system-stats.log 2>&1
CRONEOF
) | crontab -

echo "  ✓ Crontab configurato"

# =============================================================================
# Copia file dashboard HTML
# =============================================================================
echo ""
echo -e "${GREEN}Copia file dashboard HTML...${NC}"
DASHBOARD_SRC="$(cd "$(dirname "$0")" && pwd)/dashboard"
DASHBOARD_DST="${DATA_DIR}/../flask-dashboard"
sudo mkdir -p "$DASHBOARD_DST"
sudo cp "$DASHBOARD_SRC"/*.html "$DASHBOARD_DST/"
sudo cp "$DASHBOARD_SRC"/*.js "$DASHBOARD_DST/"
sudo chown -R $(logname):$(logname) "$DASHBOARD_DST"
echo "  ✓ File HTML copiati in ${DASHBOARD_DST}"

# =============================================================================
# Sostituisci placeholder nei file HTML
# =============================================================================
echo ""
echo -e "${GREEN}Configurazione dashboard HTML...${NC}"
for f in "$DASHBOARD_DST"/*.html; do
    sed -i "s|CALLSIGN_PLACEHOLDER|${CALLSIGN}|g" "$f"
    sed -i "s|LOCATION_PLACEHOLDER|${LOCATION}|g" "$f"
    sed -i "s|Reggello|${LOCATION}|g" "$f"
    echo "  ✓ $(basename $f)"
done

# =============================================================================
# Fine
# =============================================================================
echo ""
echo -e "${GREEN}============================================="
echo " Installazione completata!"
echo "=============================================${NC}"
echo ""
echo -e "  Dashboard:   ${CYAN}http://$(hostname -I | awk '{print $1}'):5000${NC}"
echo -e "  Config:      ${CYAN}${CONFIG_PATH}${NC}"
echo -e "  DB:          ${CYAN}${DATA_DIR}/aprs.db${NC}"
echo ""
echo -e "${YELLOW}Controlla i servizi con: sudo systemctl status mqtt-telegram${NC}"
