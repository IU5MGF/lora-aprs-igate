#!/bin/bash
# Rigenera config.py dal file .env

ENV_FILE="/usr/local/lib/lora-aprs/.env"
CONFIG_FILE="/usr/local/lib/lora-aprs/config.py"

if [ ! -f "$ENV_FILE" ]; then
    echo "Errore: $ENV_FILE non trovato"
    exit 1
fi

source "$ENV_FILE"

if [ "$HAS_SSD" = "True" ]; then
    DATA_DIR="${SSD_MOUNT}/radio/data"
else
    DATA_DIR="/home/$(logname)/radio/data"
fi

sudo tee "$CONFIG_FILE" > /dev/null << CONFEOF
# config.py — Generato da update-config.sh il $(date '+%Y-%m-%d %H:%M')
# NON modificare direttamente — modifica .env e riesegui update-config.sh

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
DB_RETENTION_DAYS = ${DB_RETENTION_DAYS}
TIMEZONE        = "${TIMEZONE}"
MQTT_HOST       = "localhost"
MQTT_PORT       = 1883
CONFEOF

echo "config.py rigenerato da .env"
sudo systemctl restart mqtt-telegram alerts syslog-collector flask-dashboard cleanup
echo "Servizi riavviati"
