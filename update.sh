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

echo -e "${CYAN}--- Git pull ---${NC}"
cd "$SCRIPT_DIR"
git pull
echo ""

echo -e "${CYAN}--- Copia script Python ---${NC}"
SCRIPTS="mqtt-telegram.py alerts.py cleanup.py system-stats.py daily-stats.py syslog-collector.py flask-dashboard.py"
for s in $SCRIPTS; do
    if [ -f "$SCRIPT_DIR/$s" ]; then
        sudo cp "$SCRIPT_DIR/$s" "/usr/local/bin/$s"
        echo "  ✓ $s"
    fi
done

if [ -f "$SCRIPT_DIR/mqtt-watchdog.sh" ]; then
    sudo cp "$SCRIPT_DIR/mqtt-watchdog.sh" "/usr/local/bin/mqtt-watchdog.sh"
    sudo chmod +x "/usr/local/bin/mqtt-watchdog.sh"
    echo "  ✓ mqtt-watchdog.sh"
fi

if [ -f "$SCRIPT_DIR/meshcom-poller.py" ]; then
    sudo cp "$SCRIPT_DIR/meshcom-poller.py" "/usr/local/bin/meshcom-poller.py"
    echo "  ✓ meshcom-poller.py"
fi

if [ -f "$SCRIPT_DIR/meshcom-udp-listener.py" ]; then
    sudo cp "$SCRIPT_DIR/meshcom-udp-listener.py" "/usr/local/bin/meshcom-udp-listener.py"
    echo "  ✓ meshcom-udp-listener.py"
fi
echo ""

echo -e "${CYAN}--- Copia file dashboard ---${NC}"
if [ -d "$DASHBOARD_DIR" ]; then
    sudo cp "$SCRIPT_DIR/dashboard"/*.html "$DASHBOARD_DIR/"
    sudo cp "$SCRIPT_DIR/dashboard"/*.js "$DASHBOARD_DIR/"
    sudo chown -R leonardo:leonardo "$DASHBOARD_DIR"
    echo "  ✓ File HTML/JS copiati in ${DASHBOARD_DIR}"
else
    echo -e "${YELLOW}  AVVISO: directory dashboard non trovata: ${DASHBOARD_DIR}${NC}"
fi
echo ""

echo -e "${CYAN}--- Inizializzazione DB (nuove tabelle se presenti) ---${NC}"
sudo python3 /usr/local/bin/syslog-collector.py --init-only
echo ""

echo -e "${CYAN}--- Riavvio servizi ---${NC}"
SERVICES="syslog-collector mqtt-telegram alerts cleanup flask-dashboard"
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
echo ""

echo -e "${GREEN}============================================="
echo "   Aggiornamento completato!"
echo "=============================================${NC}"
echo "=== COMPLETATO ==="
