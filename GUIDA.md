# Guida al sistema LoRa APRS iGate CALLSIGN-10

## 1. Architettura
### LoRa APRS
Radio LoRa -> CA2RXU -> syslog UDP 1514 -> syslog-collector -> SQLite -> Flask dashboard
                                                              -> mqtt-telegram -> Telegram
### MeshCom
WebUI HTTP -> meshcom-poller -> SQLite -> Flask dashboard
                             -> Telegram (solo messaggi testo)

## 2. Hardware
| Dispositivo | Callsign | Firmware | IP | Frequenza | Ruolo |
|---|---|---|---|---|---|
| LilyGo T3 v1.6.1 | CALLSIGN-10 | CA2RXU v3.2.4 | IGATE_IP | 433.775 MHz | iGate APRS |
| LilyGo T3 v1.6.1 | CALLSIGN-12 | MeshCom 4.35p | MESHCOM_IP | 433.175 MHz | Gateway MeshCom |
| Raspberry Pi 5 | - | - | RPi_IP | - | Server principale |

## 3. Servizi systemd
| Servizio | Funzione |
|---|---|
| syslog-collector | Riceve pacchetti APRS via UDP 1514, salva nel DB |
| mqtt-telegram | Notifica pacchetti su Telegram |
| alerts | Monitora silenzio RF, iGate offline, servizi down |
| cleanup | Elimina pacchetti piu vecchi di 30 giorni |
| flask-dashboard | Dashboard web porta 5000 |
| system-stats | CPU/RAM/disco ogni 15 minuti |
| daily-stats | Statistiche giornaliere a mezzanotte |
| meshcom-poller | Interroga WebUI MeshCom ogni 60 secondi |
| oled | Display OLED SSD1306 (opzionale) |

## 4. Database
File: /mnt/ssd/radio/data/aprs.db (SQLite)

### Tabella packets
| Campo | Descrizione |
|---|---|
| timestamp | Data/ora UTC |
| callsign | Nominativo stazione |
| path | Percorso pacchetto (APRS path o MESHCOM) |
| crc_ok | 1=valido, 0=errore |
| rssi | Potenza segnale in dBm |
| snr | Rapporto segnale/rumore in dB |
| distance | Distanza in km |
| lat/lon | Coordinate decimali |
| comment | Testo pacchetto |

### Tabella stations
| Campo | Descrizione |
|---|---|
| callsign | Nominativo |
| first_seen | Prima ricezione |
| last_seen | Ultima ricezione |
| total_packets | Pacchetti totali |
| max_distance | Distanza massima in km |
| best_rssi | RSSI migliore |

### Tabella daily_stats
| Campo | Descrizione |
|---|---|
| date | Data YYYY-MM-DD |
| total_packets | Pacchetti totali |
| total_rf | Pacchetti RF diretti |
| total_digi | Pacchetti digipeated |
| unique_stations | Stazioni uniche |
| best_distance | Distanza massima |
| rssi_avg | RSSI medio |
| crc_errors | Errori CRC |

### Tabella meshcom_status
| Campo | Descrizione |
|---|---|
| firmware | Versione firmware |
| battery_v | Tensione batteria in V |
| battery_pct | Percentuale batteria |
| wifi_rssi | RSSI WiFi in dBm |
| gateway_on | 1=gateway attivo |

### Tabella meshcom_mheard
| Campo | Descrizione |
|---|---|
| callsign | Nominativo nodo sentito |
| rssi | Potenza segnale in dBm |
| snr | SNR in dB |
| distance | Distanza in km |
| hardware | Tipo hardware |
| msg_type | Tipo pacchetto (POS, HEY, ecc.) |

### Tabella meshcom_rxlog
| Campo | Descrizione |
|---|---|
| src_call | Callsign sorgente |
| dst_call | Destinazione |
| path | Path RF percorso |
| rssi | Segnale in dBm |
| snr | SNR in dB |

### Tabella meshcom_messages
| Campo | Descrizione |
|---|---|
| callsign | Mittente |
| dest | Destinatario (* = tutti) |
| message | Testo messaggio |

## 5. Dashboard web
http://RPi_IP:5000 (LAN) - http://TAILSCALE_IP:5000 (Tailscale)

| Pagina | URL | Contenuto |
|---|---|---|
| Home | / | Statistiche, pacchetti recenti, top stazioni |
| Mappa | /map | Mappa OSM stazioni ultimi 60 min |
| Stazioni | /stations | Tutte le stazioni ricevute |
| Statistiche | /stats | Statistiche storiche giornaliere |
| Server | /server | Stato RPi, riavvio sistema |
| Eventi | /events | Log eventi |
| MeshCom | /meshcom | Stato nodo, nodi sentiti, log RF |
| iGate WebUI | /igate | Proxy WebUI CA2RXU |

### Badge pacchetti
| Badge | Colore | Significato |
|---|---|---|
| RF | Blu | Ricevuto direttamente via radio |
| DIGI | Verde | Ricevuto tramite digipeater |
| MESHCOM | Viola | Dalla rete MeshCom |

### Colori mappa
| Colore | Tipo |
|---|---|
| Verde #00ff9f | Stazione RF diretta |
| Giallo #ffd700 | Stazione via digipeater |
| Viola #bc8cff | Nodo MeshCom |
| Blu #00d4ff | iGate CALLSIGN-10 |

## 6. Telegram
| Bot | Funzione |
|---|---|
| BOT_TOKEN_NOTIFY | Pacchetti APRS, report giornaliero, avvio, report sistema 2h, messaggi MeshCom |
| BOT_TOKEN_ALERT | Silenzio RF, reboot, iGate offline, servizi down/up |

### Notifiche automatiche
- Pacchetto APRS: callsign, RSSI, SNR, distanza, path
- Messaggio MeshCom: mittente, destinatario, testo
- Report giornaliero: ore 8:00
- Report sistema: ogni 2 ore
- Silenzio RF: dopo 60 min senza pacchetti
- Reboot iGate: dopo 120 min silenzio
- iGate offline: dopo 30 min irraggiungibile
- Servizio down/up: notifica immediata

## 7. MeshCom
Nodo CALLSIGN-12 su 433.175 MHz come gateway Internet.
Interrogato ogni 60 secondi via HTTP (http://MESHCOM_IP).

### Tipi pacchetti MeshCom
| Tipo | Significato |
|---|---|
| POS | Beacon posizione GPS automatico |
| H | Gateway ha sentito un nodo (RSSI/SNR) |
| HG | Heartbeat nodo verso gateway (RSSI/SNR) |
| HEY | Annuncio presenza in rete |

Solo i messaggi di testo vengono notificati su Telegram.
I beacon posizione non vengono notificati per evitare flood.

## 8. Sigle e termini
| Sigla | Significato |
|---|---|
| APRS | Automatic Packet Reporting System - protocollo radio per posizioni e messaggi |
| LoRa | Long Range - tecnologia radio bassa potenza lunga distanza |
| iGate | Internet Gateway - connette rete radio APRS a Internet |
| Digipeater | Ripetitore digitale - ritrasmette pacchetti per estendere copertura |
| RF | Radio Frequency - pacchetto ricevuto direttamente |
| DIGI | Digipeated - pacchetto via uno o piu ripetitori |
| RSSI | Potenza segnale ricevuto in dBm (piu vicino a 0 = migliore) |
| SNR | Rapporto segnale/rumore in dB (piu alto = migliore) |
| CRC | Cyclic Redundancy Check - controllo integrita pacchetto |
| MeshCom | Rete mesh LoRa radioamatori per messaggi e posizioni |
| POS | Position - beacon posizione GPS |
| HG | Heartbeat Gateway - segnale vita verso gateway |
| HEY | Annuncio presenza rete MeshCom |
| dBm | Decibel milliwatt - unita misura potenza segnale |
| UTC | Coordinated Universal Time (Italia = UTC+2 estate) |
| SQLite | Database in singolo file |
| Systemd | Gestore servizi Linux |
| Poller | Script che interroga periodicamente una fonte dati |
| Tailscale | VPN mesh per accesso remoto sicuro |
| Hop | Salto - ritrasmissione da nodo intermedio |

---
*CALLSIGN-10 LoRa APRS iGate - TUA_CITTA - 73 de IU5MGF*
