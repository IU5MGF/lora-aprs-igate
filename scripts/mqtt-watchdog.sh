#!/bin/bash
# Watchdog mqtt-telegram

DB=$(python3 -c "import sys; sys.path.insert(0,'/usr/local/lib/lora-aprs'); from config import DB_PATH; print(DB_PATH)" 2>/dev/null)
CALLSIGN=$(python3 -c "import sys; sys.path.insert(0,'/usr/local/lib/lora-aprs'); from config import CALLSIGN; print(CALLSIGN)" 2>/dev/null)

ID_FILE="/tmp/mqtt_last_notified_id"
FLAG_FILE="/tmp/mqtt_watchdog_flag"

DB_LAST=$(sqlite3 $DB "SELECT MAX(id) FROM packets WHERE crc_ok=1 AND msg_type='RX' AND callsign IS NOT NULL AND callsign != '$CALLSIGN';" 2>/dev/null)

if [ -f "$ID_FILE" ]; then
    NOTIFIED_LAST=$(cat $ID_FILE)
else
    NOTIFIED_LAST=0
fi

if [ "$DB_LAST" -gt "$NOTIFIED_LAST" ] 2>/dev/null; then
    if [ ! -f "$FLAG_FILE" ]; then
        echo $(date +%s) > $FLAG_FILE
        exit 0
    fi
    FLAG_TIME=$(cat $FLAG_FILE)
    NOW=$(date +%s)
    DIFF=$(( NOW - FLAG_TIME ))
    if [ "$DIFF" -gt 1200 ]; then
        echo "$(date): mqtt-telegram bloccato da ${DIFF}s, riavvio" >> /var/log/mqtt-watchdog.log
        systemctl restart mqtt-telegram
        rm -f $FLAG_FILE
    fi
else
    rm -f $FLAG_FILE 2>/dev/null
fi
