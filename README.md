# LoRa APRS iGate — Server Software

> ⚠️ **Progetto in fase di sviluppo attivo**
> Questo software è rilasciato liberamente per la comunità radioamatoriale. Alcune funzionalità (es. pagine `/wx`, `/meshcom`) potrebbero apparire vuote su installazioni nuove finché non arrivano i primi dati, o presentare comportamenti imprevisti. Segnalazioni e contributi sono benvenuti.
> *73 de IU5MGF — ARI Valdarno (IQ5GX)*

Software completo per un iGate LoRa APRS basato su Raspberry Pi, con notifiche Telegram, dashboard web, monitoraggio sistema, supporto MeshCom e OLED opzionale.

## Caratteristiche

- Ricezione pacchetti LoRa APRS via syslog UDP dal firmware CA2RXU
- Parsing avanzato pacchetti: RF diretto, DIGI via callsign, pacchetti terza parte (gateway D-STAR/Echolink)
- Notifiche Telegram in tempo reale per ogni stazione ricevuta
- Alert separati per eventi di sistema (silenzio radio, iGate offline/online, servizi down)
- Alert Telegram per messaggi MeshCom diretti al proprio callsign
- Dashboard web Flask con mappa OpenStreetMap, heatmap RF, tracker, statistiche
- Mappa con filtro D-STAR/EL per nascondere ripetitori voce
- Icone marker dinamiche: 🚗 tracker mobili, GW gateway/digipeater (-10/-13), pallino per stazioni base
- Tracce tracker con colori dinamici per callsign (ogni tracker ha colore diverso)
- Poligono coverage RF storico (convex hull) — si espande automaticamente con nuove ricezioni
- Menu a tendina sulla mappa per finestra temporale (15 min → 24 ore)
- Aggiornamento mappa ogni 10 secondi
- Database SQLite con retention configurabile
- Esportazione CSV stazioni ricevute
- Tensione batteria iGate visibile in stat-card e popup mappa
- Report giornaliero automatico alle 08:00
- Report sistema ogni 2 ore (temperatura, RAM, SSD, uptime)
- Reboot automatico dopo 120 minuti di silenzio radio
- Aggiornamento sistema (apt update/upgrade) dalla dashboard
- Integrazione MeshCom completa (opzionale)
- Display OLED SSD1306 opzionale
- Installazione guidata interattiva
- Aggiornamento guidato con update.sh

## Hardware supportato

| Componente | Modello consigliato |
|---|---|
| Server | Raspberry Pi 4 / 5 |
| iGate LoRa | LilyGo T3 v1.6.1 con firmware [CA2RXU](https://github.com/richonguzman/LoRa_APRS_iGate) |
| Nodo MeshCom | LilyGo T3 v1.6.1 con firmware [MeshCom](https://icssw.org/meshcom/) (opzionale) |
| Tracker MeshCom | LilyGo T-Beam con firmware MeshCom (opzionale) |
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
    sudo apt install -y mosquitto mosquitto-clients sqlite3 git python3-pip
    pip3 install flask requests pytz --break-system-packages
    sudo systemctl enable mosquitto

**Passo 3 — Clona il repository**

    git clone https://github.com/IU5MGF/lora-aprs-igate.git
    cd lora-aprs-igate
    chmod +x install.sh update.sh

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
- Hai un nodo MeshCom da integrare? (s/n)

> **Nota:** Se esegui install.sh su un sistema già configurato, i valori esistenti vengono proposti come default — premi Invio per confermarli senza modifiche.

**Passo 5 — Verifica i servizi**

    sudo systemctl status syslog-collector
    sudo systemctl status mqtt-telegram
    sudo systemctl status alerts
    sudo systemctl status flask-dashboard

Tutti devono mostrare **active (running)**.

**Passo 6 — Accedi alla dashboard**

Apri il browser su un PC della stessa rete:

    http://IP_RASPBERRY:5000

## Aggiornamento

Per aggiornare il sistema a una versione più recente:

    cd lora-aprs-igate
    bash update.sh

Lo script esegue automaticamente: git pull, copia dei file aggiornati, inizializzazione DB (nuove tabelle se presenti), riavvio servizi.

## Cosa aspettarsi

- Ogni pacchetto ricevuto → notifica Telegram immediata con RSSI, SNR, distanza e path
- Ogni mattina alle 08:00 → report giornaliero RF/DIGI
- Ogni 2 ore → report sistema con temperatura, RAM, SSD, uptime
- Silenzio radio da 60 minuti → alert Telegram
- Silenzio radio da 120 minuti → reboot automatico iGate e RPi
- iGate offline/online → alert Telegram
- MeshCom offline/online → alert Telegram (se HAS_MESHCOM=True)
- Messaggio MeshCom diretto al proprio callsign → notifica speciale su bot alert

## Struttura repository

    lora-aprs-igate/
    ├── install.sh               # Installer interattivo
    ├── update.sh                # Aggiornamento guidato
    ├── README.md
    ├── GUIDA.md
    ├── dashboard/               # Template HTML dashboard
    │   ├── index.html
    │   ├── map.html
    │   ├── stations.html
    │   ├── stats.html
    │   ├── server.html
    │   ├── events.html
    │   ├── crc.html
    │   ├── wx.html
    │   ├── meshcom.html
    │   ├── igate.html
    │   └── dashboard.js
    ├── syslog-collector.py      # Riceve e parsifica pacchetti UDP
    ├── mqtt-telegram.py         # Notifiche Telegram + report
    ├── alerts.py                # Monitor sistema e alert
    ├── flask-dashboard.py       # Dashboard web Flask
    ├── cleanup.py               # Pulizia DB
    ├── daily-stats.py           # Statistiche giornaliere
    ├── system-stats.py          # Statistiche sistema
    ├── meshcom-poller.py        # Poller HTTP nodo MeshCom
    └── meshcom-udp-listener.py  # Listener UDP MeshCom porta 1799

## Servizi systemd

| Servizio | Descrizione |
|---|---|
| syslog-collector | Riceve pacchetti dall'iGate via UDP 1514 |
| mqtt-telegram | Notifiche Telegram + report giornaliero |
| alerts | Monitor silenzio, iGate/MeshCom offline, servizi down |
| cleanup | Pulizia DB ogni ora |
| flask-dashboard | Dashboard web porta 5000 |
| meshcom-poller | Polling HTTP nodo MeshCom (solo se HAS_MESHCOM=True) |
| meshcom-udp-listener | Listener UDP MeshCom porta 1799 (solo se HAS_MESHCOM=True) |
| oled | Display OLED (solo se HAS_OLED=True) |

## Dashboard web

Accessibile su `http://IP_RPi:5000`

| Pagina | Descrizione |
|---|---|
| / | Dashboard principale con statistiche giornaliere e LED stato iGate/MeshCom |
| /map | Mappa OSM con posizioni, heatmap RF, tracker con colori dinamici, coverage RF, icone marker dinamiche, filtro D-STAR/EL, finestra temporale configurabile, aggiornamento 10s |
| /stations | Registro storico stazioni ricevute con esportazione CSV |
| /stats | Grafici statistiche giornaliere RF/DIGI |
| /server | Stato RPi, reboot protetto da password, aggiornamento sistema |
| /events | Log eventi sistema |
| /crc | Log pacchetti con errore CRC (debug) |
| /wx | Meteo da sensore BME680 su nodo MeshCom (solo se HAS_MESHCOM=True) |
| /meshcom | Stato nodo MeshCom: tab Nodi sentiti, RX Log, Messaggi (solo se HAS_MESHCOM=True) |
| /igate | WebUI LilyGo iGate proxata |

## Integrazione MeshCom

Se hai un nodo MeshCom (es. LilyGo T3 con firmware MeshCom), il sistema può:
- Ricevere posizioni, telemetria e messaggi via UDP (porta 1799)
- Monitorare stato, batteria, nodi sentiti (mheard) e RX log via HTTP
- Visualizzare meteo da sensore BME680 collegato al nodo
- Notificare su Telegram messaggi ricevuti e messaggi diretti al proprio callsign
- Mostrare marker viola sulla mappa per nodi MeshCom con posizione GPS
- Alertare su Telegram quando il nodo va offline o torna online

Per attivare: durante install.sh rispondere `s` alla domanda sul nodo MeshCom, oppure impostare manualmente `HAS_MESHCOM = True` in `config.py` e configurare `MESHCOM_IP` e `MESHCOM_CALLSIGN`.

## Licenza

MIT License

## Autore

IU5MGF — Leonardo — ARI Valdarno (IQ5GX)
