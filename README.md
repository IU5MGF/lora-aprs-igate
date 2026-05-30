# LoRa APRS iGate - IU5MGF

Sistema completo per iGate LoRa APRS basato su CA2RXU + Raspberry Pi.

## Caratteristiche
- Dashboard web con mappa, statistiche, log eventi
- Notifiche Telegram pacchetti e alert
- Report giornaliero automatico
- Monitor batteria iGate
- Gestione automatica riavvii

## Requisiti Hardware
- Raspberry Pi 3/4/5
- SD card o SSD (min 32GB)
- LilyGo T3 v1.6.1 con firmware CA2RXU
- Alimentatore ufficiale RPi
- OLED SSD1306 I2C (opzionale)

## Installazione

```bash
curl -sSL https://raw.githubusercontent.com/IU5MGF/lora-aprs-igate/main/install.sh | bash
```

## Configurazione richiesta
- Callsign radioamatore
- Passcode APRS-IS
- Coordinate GPS
- Token bot Telegram
- Chat ID Telegram

## Dashboard
Accessibile su `http://IP_RASPBERRY:5000`

## Autore
IU5MGF - ARI Valdarno
