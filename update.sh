#!/bin/bash
# =============================================================================
# update.sh — Aggiornamento sistema LoRa APRS iGate
# =============================================================================
set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_PATH="/usr/local/lib/lora-aprs/config.py"

echo -e "${CYAN}"
echo "============================================="
echo "   LoRa APRS iGate — Aggiornamento sistema"
echo "============================================="
echo -e "${NC}"

# Verifica config.py
if [ ! -f "$CONFIG_PATH" ]; then
    echo -e "${RED}ERRORE: config.py non trovato. Esegui prima install.sh.${NC}"
    exit 1
fi

# Leggi DASHBOARD_DIR da config.py
DATA_DIR=$(python3 -c "
import sys
sys.path.insert(0, '/usr/local/lib/lora-aprs')
from config import DATA_DIR
print(DATA_DIR)
" 2>/dev/null)

DASHBOARD_DIR="${DATA_DIR%/data}/flask-dashboard"

# Installazione Docker (install.sh --docker): c'è il file .env con RADIO_DIR
DOCKER_MODE=0
grep -qs "^RADIO_DIR=" "$SCRIPT_DIR/.env" && DOCKER_MODE=1
[ "$DOCKER_MODE" = 1 ] && echo -e "${CYAN}Modalità Docker rilevata (.env con RADIO_DIR)${NC}"

echo -e "${CYAN}--- Git pull ---${NC}"
cd "$SCRIPT_DIR"
git pull
echo ""

echo -e "${CYAN}--- Aggiornamento config.py (impostazioni nuove) ---${NC}"
# Le installazioni vecchie non hanno le chiavi aggiunte dopo: senza, la pagina
# /settings non può salvarle. Si aggiungono con un valore predefinito.
CALLSIGN_CFG=$(python3 -c "
import sys
sys.path.insert(0, '/usr/local/lib/lora-aprs')
from config import CALLSIGN
print(CALLSIGN.upper())
" 2>/dev/null)
add_key() {  # $1 chiave, $2 riga completa da aggiungere se manca
    if ! grep -qE "^$1[[:space:]]*=" "$CONFIG_PATH"; then
        echo "$2" | sudo tee -a "$CONFIG_PATH" > /dev/null
        echo "  ✓ aggiunto $1"
    fi
}
add_key DISPLAY_NAME     "DISPLAY_NAME = \"${CALLSIGN_CFG}\""
add_key HAS_MESHCOM      "HAS_MESHCOM = False"
add_key MESHCOM_IP       'MESHCOM_IP = ""'
add_key MESHCOM_CALLSIGN 'MESHCOM_CALLSIGN = ""'
# permessi per la pagina /settings (come install.sh): config.py scrivibile e
# riavvio dei servizi senza password
USR=$(logname 2>/dev/null || whoami)
sudo chown "$USR:$USR" "$CONFIG_PATH" && sudo chmod 664 "$CONFIG_PATH"
if [ "$DOCKER_MODE" = 0 ] && ! sudo test -f /etc/sudoers.d/lora-aprs-restart; then
    echo "$USR ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart flask-dashboard, /usr/bin/systemctl restart alerts, /usr/bin/systemctl restart mqtt-telegram, /usr/bin/systemctl restart syslog-collector" | sudo tee /etc/sudoers.d/lora-aprs-restart > /dev/null
    sudo chmod 440 /etc/sudoers.d/lora-aprs-restart
    sudo visudo -c > /dev/null && echo "  ✓ regola sudo per /settings aggiunta" || { sudo rm -f /etc/sudoers.d/lora-aprs-restart; echo -e "${YELLOW}  AVVISO: regola sudo non valida, rimossa${NC}"; }
fi
echo ""

echo -e "${CYAN}--- Copia script Python ---${NC}"
SCRIPTS="mqtt-telegram.py alerts.py cleanup.py system-stats.py daily-stats.py syslog-collector.py flask-dashboard.py"
# in Docker sull'host servono solo gli script lanciati dal cron
[ "$DOCKER_MODE" = 1 ] && SCRIPTS="system-stats.py daily-stats.py"
for s in $SCRIPTS; do
    if [ -f "$SCRIPT_DIR/$s" ]; then
        sudo cp "$SCRIPT_DIR/$s" "/usr/local/bin/$s"
        echo "  ✓ $s"
    fi
done

if [ "$DOCKER_MODE" = 0 ] && [ -f "$SCRIPT_DIR/mqtt-watchdog.sh" ]; then
    sudo cp "$SCRIPT_DIR/mqtt-watchdog.sh" "/usr/local/bin/mqtt-watchdog.sh"
    sudo chmod +x "/usr/local/bin/mqtt-watchdog.sh"
    echo "  ✓ mqtt-watchdog.sh"
fi

if [ "$DOCKER_MODE" = 0 ] && [ -f "$SCRIPT_DIR/meshcom-poller.py" ]; then
    sudo cp "$SCRIPT_DIR/meshcom-poller.py" "/usr/local/bin/meshcom-poller.py"
    echo "  ✓ meshcom-poller.py"
fi

if [ "$DOCKER_MODE" = 0 ] && [ -f "$SCRIPT_DIR/meshcom-udp-listener.py" ]; then
    sudo cp "$SCRIPT_DIR/meshcom-udp-listener.py" "/usr/local/bin/meshcom-udp-listener.py"
    echo "  ✓ meshcom-udp-listener.py"
fi
echo ""

echo -e "${CYAN}--- Copia file dashboard ---${NC}"
if [ -d "$DASHBOARD_DIR" ]; then
    sudo cp "$SCRIPT_DIR/dashboard"/*.html "$DASHBOARD_DIR/"
    sudo cp "$SCRIPT_DIR/dashboard"/*.js "$DASHBOARD_DIR/"
    sudo chown -R "$USR:$USR" "$DASHBOARD_DIR"
    echo "  ✓ File HTML/JS copiati in ${DASHBOARD_DIR}"
    # come install.sh: le pagine nascono con la località dell'autore, si mette la propria
    LOCATION_CFG=$(python3 -c "
import sys
sys.path.insert(0, '/usr/local/lib/lora-aprs')
from config import LOCATION
print(LOCATION)
" 2>/dev/null || true)
    if [ -n "$LOCATION_CFG" ] && [ "$LOCATION_CFG" != "Reggello" ]; then
        LOC_SED=$(printf '%s' "$LOCATION_CFG" | sed 's/[&|\\]/\\&/g')
        sudo sed -i "s|Reggello|${LOC_SED}|g" "$DASHBOARD_DIR"/*.html
        echo "  ✓ località impostata: ${LOCATION_CFG}"
    fi
else
    echo -e "${YELLOW}  AVVISO: directory dashboard non trovata: ${DASHBOARD_DIR}${NC}"
fi
echo ""

if [ "$DOCKER_MODE" = 1 ]; then
    DC="docker compose"
    docker info >/dev/null 2>&1 || DC="sudo docker compose"
    echo -e "${CYAN}--- Ricostruzione e riavvio container ---${NC}"
    cd "$SCRIPT_DIR"
    # container MeshCom (profilo "meshcom") solo se HAS_MESHCOM = True in config.py
    if grep -qE "^HAS_MESHCOM[[:space:]]*=[[:space:]]*True" "$CONFIG_PATH"; then
        grep -q "^COMPOSE_PROFILES=.*meshcom" .env || { echo "COMPOSE_PROFILES=meshcom" >> .env; echo "  ✓ MeshCom attivato nel .env"; }
    else
        sed -i "/^COMPOSE_PROFILES=meshcom$/d" .env
        if [ -n "$($DC --profile meshcom ps -q meshcom-poller meshcom-udp-listener 2>/dev/null)" ]; then
            $DC --profile meshcom rm -sf meshcom-poller meshcom-udp-listener
            echo "  ✓ container MeshCom tolti (HAS_MESHCOM = False)"
        fi
    fi
    $DC build
    $DC run --rm --no-deps syslog-collector python3 syslog-collector.py --init-only
    $DC up -d
    echo ""
    echo -e "${GREEN}============================================="
    echo "   Aggiornamento completato (Docker)!"
    echo -e "=============================================${NC}"
    echo "=== COMPLETATO ==="
    exit 0
fi

echo -e "${CYAN}--- Inizializzazione DB (nuove tabelle se presenti) ---${NC}"
sudo python3 /usr/local/bin/syslog-collector.py --init-only
echo ""

echo -e "${CYAN}--- Riavvio servizi ---${NC}"
SERVICES="syslog-collector mqtt-telegram alerts cleanup"
for svc in $SERVICES; do
    if systemctl list-unit-files | grep -q "^${svc}.service"; then
        sudo systemctl restart "$svc" 2>/dev/null && echo "  ✓ $svc riavviato" || echo -e "${YELLOW}  AVVISO: $svc non trovato${NC}"
    fi
done

for svc in meshcom-poller meshcom-udp-listener; do
    if systemctl list-unit-files | grep -q "^${svc}.service"; then
        sudo systemctl restart "$svc" 2>/dev/null && echo "  ✓ $svc riavviato"
    fi
done
# Verifica/ripristino cron system-stats (auto-guarigione se manca)
if ! crontab -l 2>/dev/null | grep -q "system-stats.py"; then
    echo -e "${YELLOW}  cron system-stats.py mancante, lo ripristino...${NC}"
    (crontab -l 2>/dev/null || true; echo "*/15 * * * * /usr/bin/python3 /usr/local/bin/system-stats.py >> ${DATA_DIR}/system-stats.log 2>&1") | crontab -
    echo "  ✓ cron system-stats.py ripristinato"
fi
# flask-dashboard per ultimo, e fuori dal suo servizio: se update.sh è stato
# lanciato dalla dashboard, un riavvio diretto ucciderebbe anche questo script
# (e il blocco /tmp/system-update.running resterebbe lì)
sudo systemd-run --quiet --collect --on-active=3 /usr/bin/systemctl restart flask-dashboard \
    && echo "  ✓ flask-dashboard si riavvia tra 3 secondi" \
    || { sudo systemctl restart flask-dashboard 2>/dev/null && echo "  ✓ flask-dashboard riavviato"; }
echo ""

echo -e "${GREEN}============================================="
echo "   Aggiornamento completato!"
echo -e "=============================================${NC}"
echo "=== COMPLETATO ==="
