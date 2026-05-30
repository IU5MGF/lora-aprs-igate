#!/bin/bash
# Watchdog mqtt-telegram
# Se ci sono pacchetti nuovi nel DB ma l'ID notificato non avanza da 20+ min -> riavvia

DB="/mnt/ssd/radio/data/aprs.db"
ID_FILE="/tmp/mqtt_last_notified_id"
FLAG_FILE="/tmp/mqtt_watchdog_flag"

# ultimo ID nel DB con callsign valido
DB_LAST=$(sqlite3 $DB "SELECT MAX(id) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != 'IU5MGF-10';")

# ultimo ID notificato
if [ -f "$ID_FILE" ]; then
    NOTIFIED_LAST=$(cat $ID_FILE)
else
    NOTIFIED_LAST=0
fi

# se DB ha pacchetti più recenti di quelli notificati
if [ "$DB_LAST" -gt "$NOTIFIED_LAST" ] 2>/dev/null; then
    # primo rilevamento: salva flag con timestamp
    if [ ! -f "$FLAG_FILE" ]; then
        echo $(date +%s) > $FLAG_FILE
        exit 0
    fi
    # controlla da quanto tempo
    FLAG_TIME=$(cat $FLAG_FILE)
    NOW=$(date +%s)
    DIFF=$(( NOW - FLAG_TIME ))
    if [ "$DIFF" -gt 1200 ]; then
        echo "$(date): mqtt-telegram bloccato da ${DIFF}s, riavvio" >> /var/log/mqtt-watchdog.log
        systemctl restart mqtt-telegram
        rm -f $FLAG_FILE
    fi
else
    # tutto ok, rimuovi flag
    rm -f $FLAG_FILE 2>/dev/null
fi
