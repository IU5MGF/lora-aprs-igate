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

## Getting Started

**Cosa serve prima di iniziare:**
- Raspberry Pi 4 o 5 con Raspberry Pi OS
- LilyGo T3 v1.6.1 con firmware CA2RXU configurato
- Un bot Telegram (creato con @BotFather) e il tuo Chat ID (da @userinfobot)

**Passo 1 — Configura il syslog nel firmware CA2RXU**

Nel pannello web del LilyGo imposta:

    Syslog Server IP: IP del tuo Raspberry Pi
    Syslog Port: 1514

**Passo 2 — Installa i prerequisiti sul Raspberry Pi**

    sudo apt update
    sudo apt install -y mosquitto mosquitto-clients sqlite3 git
    sudo systemctl enable mosquitto

**Passo 3 — Clona il repository**

    git clone https://github.com/IU5MGF/lora-aprs-igate.git
    cd lora-aprs-igate
    chmod +x install.sh

**Passo 4 — Avvia l'installer interattivo**

    ./install.sh

L'installer chiederà uno per uno:
- Callsign iGate (es. IZ5XXX-10)
- IP del LilyGo (es. 192.168.1.50)
- Password per il reboot dalla dashboard
- Token bot Telegram notifiche
- Chat ID Telegram notifiche
- Stesso bot per gli alert? (s/n)
- Latitudine e longitudine della stazione
- Hai un SSD collegato? (s/n)
- Hai un display OLED? (s/n)
- Retention DB in giorni (default 30)
- Timezone (default Europe/Rome)

**Passo 5 — Verifica i servizi**

    sudo systemctl status syslog-collector
    sudo systemctl status mqtt-telegram
    sudo systemctl status alerts
    sudo systemctl status flask-dashboard

Tutti devono mostrare **active (running)**.

**Passo 6 — Accedi alla dashboard**

Apri il browser su un PC della stessa rete:

    http://IP_RASPBERRY:5000

## Cosa aspettarsi

- Ogni pacchetto ricevuto → notifica Telegram immediata
- Ogni mattina alle 08:00 → report giornaliero RF/DIGI
- Ogni 2 ore → report sistema con temperatura, RAM, SSD, uptime
- Silenzio radio da 60 minuti → alert Telegram
- Silenzio radio da 120 minuti → reboot automatico iGate e RPi

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

