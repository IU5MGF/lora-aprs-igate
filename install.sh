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

# Leggi valori esistenti da config.py se presente
CONFIG_PATH="/usr/local/lib/lora-aprs/config.py"
if [ -f "$CONFIG_PATH" ]; then
    echo -e "${YELLOW}config.py esistente trovato — i valori attuali verranno usati come default.${NC}"
    _read_cfg() { python3 -c "
import re, sys
for line in open('$CONFIG_PATH'):
    m = re.match(r'^' + sys.argv[1] + r'\s*=\s*\"(.*)\"', line)
    if m: print(m.group(1)); break
" "$1" 2>/dev/null; }
    _read_cfg_bare() { python3 -c "
import re, sys
for line in open('$CONFIG_PATH'):
    m = re.match(r'^' + sys.argv[1] + r'\s*=\s*(.*)', line)
    if m: print(m.group(1).strip()); break
" "$1" 2>/dev/null; }
    DEF_CALLSIGN=$(_read_cfg "CALLSIGN")
    DEF_IGATE_IP=$(_read_cfg "IGATE_IP")
    DEF_REBOOT_PW=$(_read_cfg "IGATE_REBOOT_PW")
    DEF_BOT_NOTIFY=$(_read_cfg "BOT_TOKEN_NOTIFY")
    DEF_CHAT_NOTIFY=$(_read_cfg "CHAT_ID_NOTIFY")
    DEF_BOT_ALERT=$(_read_cfg "BOT_TOKEN_ALERT")
    DEF_CHAT_ALERT=$(_read_cfg "CHAT_ID_ALERT")
    DEF_LAT=$(_read_cfg_bare "LATITUDE")
    DEF_LON=$(_read_cfg_bare "LONGITUDE")
    DEF_LOCATION=$(_read_cfg "LOCATION")
    DEF_TIMEZONE=$(_read_cfg "TIMEZONE")
    DEF_DB_RETENTION=$(_read_cfg_bare "DB_RETENTION_DAYS")
    DEF_MESHCOM_IP=$(_read_cfg "MESHCOM_IP")
    DEF_MESHCOM_CALLSIGN=$(_read_cfg "MESHCOM_CALLSIGN")
else
    DEF_CALLSIGN=""; DEF_IGATE_IP="192.168.2.10"; DEF_REBOOT_PW="raspberry"
    DEF_BOT_NOTIFY=""; DEF_CHAT_NOTIFY=""; DEF_BOT_ALERT=""; DEF_CHAT_ALERT=""
    DEF_LAT="43.6800"; DEF_LON="11.5300"; DEF_LOCATION="Reggello"
    DEF_TIMEZONE="Europe/Rome"; DEF_DB_RETENTION="30"
    DEF_MESHCOM_IP="192.168.2.12"; DEF_MESHCOM_CALLSIGN=""
fi

echo -e "${CYAN}--- Configurazione iGate ---${NC}"
CALLSIGN=$(ask "Callsign iGate (es. IZ5XXX-10)" "$DEF_CALLSIGN")
IGATE_IP=$(ask "IP locale iGate" "${DEF_IGATE_IP:-192.168.2.10}")
IGATE_REBOOT_PW=$(ask "Password reboot iGate" "${DEF_REBOOT_PW:-raspberry}")

echo ""
echo -e "${CYAN}--- Telegram notifiche pacchetti ---${NC}"
BOT_TOKEN_NOTIFY=$(ask "Bot Token Telegram (notifiche)" "$DEF_BOT_NOTIFY")
CHAT_ID_NOTIFY=$(ask "Chat ID Telegram (notifiche)" "$DEF_CHAT_NOTIFY")

echo ""
echo -e "${CYAN}--- Telegram alert sistema ---${NC}"
SAME_BOT=$(ask_yn "Usare lo stesso bot anche per gli alert?" "s")
if [ "$SAME_BOT" = "True" ]; then
    BOT_TOKEN_ALERT="$BOT_TOKEN_NOTIFY"
    CHAT_ID_ALERT="$CHAT_ID_NOTIFY"
else
    BOT_TOKEN_ALERT=$(ask "Bot Token Telegram (alert)" "$DEF_BOT_ALERT")
    CHAT_ID_ALERT=$(ask "Chat ID Telegram (alert)" "$DEF_CHAT_ALERT")
fi

echo ""
echo -e "${CYAN}--- Posizione iGate ---${NC}"
echo -e "${YELLOW}Inserisci le coordinate del punto in cui e' installato il tuo iGate/Digipeater.${NC}"
echo -e "${YELLOW}Servono a calcolare correttamente la copertura RF (poligono, distanze, heatmap) da quel punto.${NC}"
LATITUDE=$(ask "Latitudine decimale (es. 43.68047)" "${DEF_LAT:-43.68047}")
LONGITUDE=$(ask "Longitudine decimale (es. 11.52987)" "${DEF_LON:-11.52987}")

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
    DATA_DIR="/home/$(logname)/radio/data"
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
echo -e "${CYAN}--- MeshCom (opzionale) ---${NC}"
HAS_MESHCOM=$(ask_yn "Hai un nodo MeshCom da integrare?" "n")
if [ "$HAS_MESHCOM" = "True" ]; then
    MESHCOM_IP=$(ask "IP locale nodo MeshCom" "${DEF_MESHCOM_IP:-192.168.2.12}")
    MESHCOM_CALLSIGN=$(ask "Callsign nodo MeshCom" "${DEF_MESHCOM_CALLSIGN:-}")
else
    MESHCOM_IP=""
    MESHCOM_CALLSIGN=""
fi

echo ""
echo -e "${CYAN}--- Database ---${NC}"
DB_RETENTION=$(ask "Retention pacchetti (giorni)" "${DEF_DB_RETENTION:-30}")

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
LOCATION        = "${LOCATION}"

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
HAS_MESHCOM     = ${HAS_MESHCOM}
MESHCOM_IP      = "${MESHCOM_IP}"
MESHCOM_CALLSIGN = "${MESHCOM_CALLSIGN}"
CONFEOF

echo -e "${GREEN}config.py scritto in ${CONFIG_PATH}${NC}"
# Permessi scrittura per la pagina /settings + regola sudo per auto-restart dei servizi
sudo chown "$(whoami):$(whoami)" "$CONFIG_PATH"
sudo chmod 664 "$CONFIG_PATH"
echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart flask-dashboard, /usr/bin/systemctl restart alerts, /usr/bin/systemctl restart mqtt-telegram, /usr/bin/systemctl restart syslog-collector" | sudo tee /etc/sudoers.d/lora-aprs-restart > /dev/null
sudo chmod 440 /etc/sudoers.d/lora-aprs-restart
sudo visudo -c > /dev/null && echo -e "${GREEN}Permessi /settings configurati (scrittura config.py + auto-restart servizi)${NC}" || echo -e "${YELLOW}Attenzione: verifica manuale sudoers necessaria${NC}"

# Genera .env
ENV_PATH="/usr/local/lib/lora-aprs/.env"
sudo tee "$ENV_PATH" > /dev/null << ENVEOF
CALLSIGN=${CALLSIGN}
IGATE_IP=${IGATE_IP}
IGATE_REBOOT_PW=${IGATE_REBOOT_PW}
BOT_TOKEN_NOTIFY=${BOT_TOKEN_NOTIFY}
CHAT_ID_NOTIFY=${CHAT_ID_NOTIFY}
BOT_TOKEN_ALERT=${BOT_TOKEN_ALERT}
CHAT_ID_ALERT=${CHAT_ID_ALERT}
LATITUDE=${LATITUDE}
LONGITUDE=${LONGITUDE}
LOCATION=${LOCATION}
HAS_SSD=${HAS_SSD}
SSD_MOUNT=${SSD_MOUNT}
HAS_OLED=${HAS_OLED}
OLED_I2C_ADDR=${OLED_I2C_ADDR}
DB_RETENTION_DAYS=${DB_RETENTION}
TIMEZONE=${TIMEZONE}
ENVEOF
echo -e "${GREEN}.env scritto in ${ENV_PATH}${NC}"

# =============================================================================
# Configura mosquitto
# =============================================================================
echo ""
echo -e "${GREEN}Configurazione mosquitto...${NC}"
if ! grep -q "listener 1883" /etc/mosquitto/mosquitto.conf 2>/dev/null; then
    sudo tee /etc/mosquitto/conf.d/lora-aprs.conf > /dev/null << MQTTEOF
listener 1883
allow_anonymous true
MQTTEOF
    echo "  ✓ mosquitto configurato"
else
    echo "  ✓ mosquitto già configurato"
fi
sudo systemctl restart mosquitto

# =============================================================================
# Installa dipendenze Python
# =============================================================================
echo ""
echo -e "${GREEN}Installazione dipendenze Python...${NC}"
sudo apt install -y python3-pip 2>/dev/null || true
sudo pip3 install paho-mqtt requests pytz flask --break-system-packages 2>/dev/null || python3 -m pip install paho-mqtt requests pytz flask --break-system-packages

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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

echo -e "${CYAN}--- Inizializzazione database ---${NC}"
sudo python3 /usr/local/bin/syslog-collector.py --init-only
sudo chown -R $(logname):$(logname) "$DATA_DIR" 2>/dev/null || true
echo -e "${GREEN}Database inizializzato.${NC}"

install_service "syslog-collector" "LoRa APRS Syslog Collector"   "/usr/bin/python3 /usr/local/bin/syslog-collector.py"
install_service "mqtt-telegram"    "LoRa APRS MQTT Telegram"      "/usr/bin/python3 /usr/local/bin/mqtt-telegram.py"
install_service "alerts"           "LoRa APRS Alerts"             "/usr/bin/python3 /usr/local/bin/alerts.py"
install_service "cleanup"          "LoRa APRS DB Cleanup"         "/usr/bin/python3 /usr/local/bin/cleanup.py"
install_service "flask-dashboard"  "LoRa APRS Flask Dashboard"    "/usr/bin/python3 /usr/local/bin/flask-dashboard.py"

if [ "$HAS_OLED" = "True" ]; then
    install_service "oled" "LoRa APRS OLED Display" "/usr/bin/python3 ${SSD_MOUNT}/oled/oled.py"
fi

if [ "$HAS_MESHCOM" = "True" ]; then
    if [ -f "$SCRIPT_DIR/meshcom-poller.py" ]; then
        sudo cp "$SCRIPT_DIR/meshcom-poller.py" "/usr/local/bin/meshcom-poller.py"
        sudo chmod +x "/usr/local/bin/meshcom-poller.py"
        echo "  ✓ meshcom-poller.py"
    fi
    install_service "meshcom-poller" "MeshCom WebUI Poller" "/usr/bin/python3 /usr/local/bin/meshcom-poller.py"

    if [ -f "$SCRIPT_DIR/meshcom-udp-listener.py" ]; then
        sudo cp "$SCRIPT_DIR/meshcom-udp-listener.py" "/usr/local/bin/meshcom-udp-listener.py"
        sudo chmod +x "/usr/local/bin/meshcom-udp-listener.py"
        echo "  ✓ meshcom-udp-listener.py"
    fi
    install_service "meshcom-udp-listener" "MeshCom UDP Listener (porta 1799)" "/usr/bin/python3 /usr/local/bin/meshcom-udp-listener.py"

    echo ""
    echo -e "${YELLOW}IMPORTANTE: per attivare l'interfaccia UDP sul nodo MeshCom, collegati via seriale (USB)${NC}"
    echo -e "${YELLOW}e invia i comandi:${NC}"
    echo -e "${CYAN}  --extudpip $(hostname -I | awk '{print $1}')${NC}"
    echo -e "${CYAN}  --extudp on${NC}"
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
30 3 * * * curl -s -X POST "http://${IGATE_IP}/action" -d "type=reboot"
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
    sed -i "s|LAT_PLACEHOLDER|${LATITUDE}|g" "$f"
    sed -i "s|LON_PLACEHOLDER|${LONGITUDE}|g" "$f"
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
echo -e ""
echo -e "${YELLOW}⚠️  Questo sistema è in fase di sviluppo attivo.${NC}"
echo -e "${YELLOW}   Alcune pagine (es. /wx, /meshcom) potrebbero apparire vuote${NC}"
echo -e "${YELLOW}   finché non arrivano i primi dati dal nodo LoRa.${NC}"
echo -e "${YELLOW}   Per segnalazioni: https://github.com/IU5MGF/lora-aprs-igate${NC}"
echo -e "${YELLOW}   73 de IU5MGF — ARI Valdarno (IQ5GX)${NC}"
echo ""
echo -e "${YELLOW}Controlla i servizi con: sudo systemctl status mqtt-telegram${NC}"
