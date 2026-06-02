# LoRa APRS iGate — Server Software

Software completo per un iGate LoRa APRS basato su Raspberry Pi, con notifiche Telegram, dashboard web, monitoraggio sistema e supporto OLED opzionale.

## Caratteristiche

- Ricezione pacchetti LoRa APRS via syslog UDP dal firmware CA2RXU
- Notifiche Telegram in tempo reale per ogni stazione ricevuta
- Alert separati per eventi di sistema (silenzio radio, iGate offline, servizi down)
- Dashboard web Flask con mappa OpenStreetMap, heatmap RF, tracker, statistiche
- Database SQLite con retention configurabile
- Report giornaliero automatico alle 08:00
- Report sistema ogni 2 ore (temperatura, RAM, SSD, uptime)
- Reboot automatico dopo 120 minuti di silenzio radio
- Display OLED SSD1306 opzionale
- Installazione guidata interattiva

## Hardware supportato

| Componente | Modello consigliato |
|---|---|
| Server | Raspberry Pi 4 / 5 |
| iGate LoRa | LilyGo T3 v1.6.1 con firmware [CA2RXU](https://github.com/richonguzman/LoRa_APRS_iGate) |
| Storage | SSD via USB (opzionale ma consigliato) |
| Display | OLED SSD1306 I2C 128x64 (opzionale) |

## Struttura repository

    lora-aprs-igate/
    ├── install.sh
    ├── config.py
    ├── scripts/
    │   ├── syslog-collector.py
    │   ├── mqtt-telegram.py
    │   ├── alerts.py
    │   ├── cleanup.py
    │   ├── daily-stats.py
    │   ├── system-stats.py
    │   ├── flask-dashboard.py
    │   ├── mqtt-watchdog.sh
    │   └── oled.py

## Installazione

    git clone https://github.com/IU5MGF/lora-aprs-igate.git
    cd lora-aprs-igate
    chmod +x install.sh
    ./install.sh

L'installer chiederà: callsign, IP iGate, token Telegram, coordinate GPS, presenza SSD e OLED, retention DB, timezone.

## Configurazione iGate (firmware CA2RXU)

Nel firmware CA2RXU abilita il syslog verso l'IP del Raspberry Pi:

    Syslog Server IP: 192.168.x.x
    Syslog Port: 1514

## Servizi systemd

| Servizio | Descrizione |
|---|---|
| syslog-collector | Riceve pacchetti dall'iGate via UDP 1514 |
| mqtt-telegram | Notifiche Telegram + report giornaliero |
| alerts | Monitor silenzio, iGate offline, servizi down |
| cleanup | Pulizia DB ogni ora |
| flask-dashboard | Dashboard web porta 5000 |
| oled | Display OLED (solo se HAS_OLED=True) |

## Dashboard web

Accessibile su http://IP_RPi:5000

| Pagina | Descrizione |
|---|---|
| / | Dashboard principale con statistiche giornaliere |
| /map | Mappa OSM con posizioni, heatmap RF, tracce tracker |
| /stations | Registro storico stazioni ricevute |
| /stats | Grafici statistiche giornaliere RF/DIGI |
| /server | Stato RPi con reboot protetto da password |
| /events | Log eventi sistema |

## Licenza

MIT License

## Autore

IU5MGF — Leonardo

