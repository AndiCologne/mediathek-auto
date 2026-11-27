# mediathek-auto

![Mediathek-Auto – ein Comic-Auto mit Filmrollen als Rädern und einem Kinositz auf dem Dach](assets/mediathek-auto.png)

Lädt automatisch gut bewertete Spielfilme aus den Mediatheken von ARD und ZDF herunter, inklusive arte, 3sat und der Dritten Programme. Die Filme werden mit HandBrakeCLI umcodiert und als `Titel (Jahr)/Titel (Jahr).mp4` abgelegt. Nach jedem Lauf kommt ein Bericht per iMessage. Läuft auf macOS, einmal pro Woche, und nutzt nur die Python-Standardbibliothek.

## So funktioniert es

1. Das Skript lädt die aktuelle [MediathekView](https://mediathekview.de)-Filmliste. Es ist dieselbe Liste, die auch die App MediathekView nutzt.
2. Es filtert Spielfilme heraus: passende Länge, ohne Hörfassung, Gebärdensprache, klare Sprache, Originalfassung, Krimireihen und Mehrteiler.
3. Es gleicht die Filme mit den [IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/) ab. Titel, Produktionsjahr und Laufzeit müssen passen, Dokumentarfilme werden ausgeschlossen.
4. Geladen wird, was die Grenzen in `config.json` erfüllt. Voreingestellt sind eine IMDb-Wertung ab 8.0, mehr als 2.500 Bewertungen, Erscheinungsjahr ab 1970 und eine Länge von 70 bis 240 Minuten.
5. Filme, die schon in `Heruntergeladene_Filme.txt` stehen, werden übersprungen.
6. Heruntergeladen wird immer die beste verfügbare Videospur mit deutscher Tonspur (ohne Hörfassung). Danach prüft das Skript, ob der Download vollständig ist.
7. HandBrakeCLI codiert den Film um (Standard-Preset: „Apple 1080p30 Surround“), und die Länge wird noch einmal geprüft.
8. Der Film wird als `<Zielordner>/Titel (Jahr)/Titel (Jahr).mp4` abgelegt und in `Heruntergeladene_Filme.txt` eingetragen.
9. Zum Schluss kommt eine iMessage mit den neuen Filmen, eventuellen Fehlern und dem freien Speicherplatz.

## Ordnerstruktur

Der Code liegt in einem versteckten Unterordner des Zielordners:

```
/Volumes/TB4SSD/AILocalSandbox/Movies/        ← Zielordner (in config.json einstellbar)
├── Heruntergeladene_Filme.txt                ← Liste der vorhandenen Filme
├── Der Pate (1972)/Der Pate (1972).mp4       ← fertige Filme, je ein Ordner
├── …
└── .mediathek-auto/                          ← Code-Ordner (versteckt, im Finder: ⌘⇧.)
    ├── mediathek_auto.py                     ← das Skript
    ├── config.json                           ← alle Einstellungen
    ├── install.sh / uninstall.sh             ← wöchentlichen Zeitplan ein- und ausschalten
    ├── README.md
    ├── cache/   Filmliste und IMDb-Daten (etwa 1 GB, wöchentlich erneuert)
    ├── logs/    Protokoll und Bericht (report_*.md) je Lauf, nach 60 Tagen automatisch gelöscht
    ├── state/   interne Listen (geladene, fehlgeschlagene Filme, Zuordnungen von Hand)
    └── tmp/     Zwischendateien während eines Laufs
```

## Voraussetzungen

- macOS mit Python 3.9 oder neuer, z. B. über die Xcode Command Line Tools oder `brew install python`
- HandBrakeCLI: `brew install handbrake`
- ffmpeg und ffprobe: `brew install ffmpeg`. Gebraucht für Streams (m3u8, z. B. arte), für die Wahl der deutschen Tonspur und für die Prüfung, ob ein Download vollständig ist.

## Einrichten

```bash
# 1. Code in den versteckten Ordner im Zielordner legen
git clone https://github.com/AndiCologne/mediathek-auto.git "/Volumes/TB4SSD/AILocalSandbox/Movies/.mediathek-auto"
cd "/Volumes/TB4SSD/AILocalSandbox/Movies/.mediathek-auto"

# 2. config.json anlegen und anpassen (Zielordner, iMessage-Adresse, Grenzen)
python3 mediathek_auto.py --config-erstellen
open -e config.json

# 3. Wöchentlichen Zeitplan einrichten (Mittwoch 02:00 Uhr) und Test-iMessage senden
bash install.sh
```

Wenn macOS fragt, ob Python „Nachrichten“ steuern darf, klickst du auf **Erlauben**. Ohne diese Erlaubnis bleibt die nächtliche iMessage an der Rückfrage hängen.

## Einstellungen: `config.json`

Alle Einstellungen stehen in `config.json` im Code-Ordner. Jeder Eintrag besteht aus einem **`wert`**, den du ändern kannst, und einer **`info`**, die ihn erklärt. Die Änderungen gelten ab dem nächsten Lauf.

```json
"ANPASSBAR": {
  "imdb_wertung_mindestens": {
    "wert": 8.0,
    "info": "Nur Filme mit dieser IMDb-Wertung oder höher, z. B. 8.0."
  },
  …
}
```

### ANPASSBAR: die wichtigsten Einstellungen

| Eintrag | Voreinstellung | Bedeutung |
|---|---|---|
| `zielordner` | `/Volumes/TB4SSD/AILocalSandbox/Movies` | Ordner für die fertigen Filme. Hier liegt auch `Heruntergeladene_Filme.txt`. |
| `imdb_wertung_mindestens` | `8.0` | IMDb-Wertung mindestens, der Wert selbst zählt mit |
| `imdb_bewertungen_mehr_als` | `2500` | Der Film braucht mehr IMDb-Bewertungen als diese Zahl |
| `laenge_mindestens_minuten` | `70` | Kürzere Sendungen werden ignoriert |
| `laenge_hoechstens_minuten` | `240` | Längere Sendungen werden ignoriert (`0` = keine Obergrenze) |
| `erscheinungsjahr_ab` | `1970` | Erscheinungsjahr laut IMDb mindestens (`0` = alle Jahre) |
| `imessage_empfaenger` | leer | Telefonnummer (+49…) oder Apple-ID-E-Mail für den Bericht. Leer = keine iMessage. |

### WEITERE_EINSTELLUNGEN

| Eintrag | Voreinstellung | Bedeutung |
|---|---|---|
| `filme_pro_lauf_hoechstens` | `15` | Höchstzahl neuer Filme pro Lauf |
| `freier_speicher_mindestens_gb` | `30` | So viel bleibt im Zielordner frei, sonst stoppt der Lauf |
| `handbrake_preset` | `Apple 1080p30 Surround` | HandBrake-Preset |
| `handbrake_programm` | `/opt/homebrew/bin/HandBrakeCLI` | Pfad zu HandBrakeCLI |
| `dateiendung` | `.mp4` | Dateiendung der fertigen Filme |
| `sender` | ARD, ZDF, ARTE.DE, 3Sat, Dritte … | Berücksichtigte Sender, wie sie in MediathekView heißen |
| `imessage_auch_ohne_neue_filme` | `true` | Auch dann eine iMessage, wenn nichts Neues dabei war |
| `mac_mitteilung` | `true` | Zusätzlich eine Mitteilung auf dem Mac |
| `logs_aufbewahren_tage` | `60` | Ältere Logs und Berichte werden automatisch gelöscht |

Eine vollständige Vorlage steht in [`config.example.json`](config.example.json).

## Liste der vorhandenen Filme: `Heruntergeladene_Filme.txt`

Die Liste liegt im Zielordner. Jeder geladene Film wird dort eingetragen:

```
Der Pate (1972) | IMDb 9.2
Parasite (2019) | IMDb 8.5
```

Du kannst die Liste von Hand um Filme ergänzen, die du schon hast. Es reicht `Titel (Jahr)`. Das Skript ordnet jede Zeile über Titel und Jahr einem IMDb-Film zu. Deshalb wird ein Film auch dann übersprungen, wenn die Mediathek ihn anders nennt, zum Beispiel „Apocalypse Now (1979)“ in der Liste und „Apocalypse Now – Final Cut“ in der Mediathek.

Titel, die IMDb anders schreibt (Tippfehler, abweichendes Jahr), lassen sich in `state/extra_ids.json` von Hand einer IMDb-ID zuordnen:

```json
{ "tt0071562": "Der Pate - Teil II (1974)" }
```

## Befehle

Alle Befehle werden im Code-Ordner ausgeführt (`cd "/Volumes/TB4SSD/AILocalSandbox/Movies/.mediathek-auto"`):

```bash
python3 mediathek_auto.py                    # normaler Lauf (wie mittwochs)
python3 mediathek_auto.py --dry-run          # nur suchen, Bericht in logs/report_*_dryrun.md
python3 mediathek_auto.py --limit 1          # höchstens einen Film laden
python3 mediathek_auto.py --test-imessage    # Test-iMessage senden
python3 mediathek_auto.py --config-erstellen # config.json im beschrifteten Format (neu) schreiben
launchctl kickstart gui/$(id -u)/local.mediathek-auto   # Hintergrund-Lauf sofort starten
pkill -f mediathek_auto.py                   # laufenden Durchgang abbrechen
bash uninstall.sh                            # Zeitplan entfernen
```

## Wenn etwas nicht klappt

- **Was ist passiert?** Für jeden Lauf gibt es in `logs/` ein Protokoll (`*.log`) und einen Bericht (`report_*.md`). Dazu kommen `handbrake-last.log`, `ffmpeg-last.log` und `last_playlist.m3u8` vom letzten Film.
- **„Operation not permitted“ im Log:** macOS verweigert dem Hintergrund-Lauf den Zugriff auf das externe Laufwerk. Abhilfe: Systemeinstellungen → Datenschutz & Sicherheit → Festplattenvollzugriff → das Python hinzufügen, das `install.sh` anzeigt.
- **Ein Film schlägt immer wieder fehl:** Nach 3 Fehlversuchen wird er nicht mehr versucht (`state/failed.json`). Wird der Eintrag dort gelöscht, versucht das Skript ihn erneut.
- **„Es läuft bereits ein anderer Durchgang“:** Es läuft schon ein Durchgang. Warte, bis er fertig ist, oder brich ihn mit `pkill -f mediathek_auto.py` ab.

## Hinweise

- Die IMDb-Daten sind nur für den privaten, nicht kommerziellen Gebrauch freigegeben.
- Die Filme der Mediatheken sind für den privaten Gebrauch bestimmt. Gib sie nicht weiter.
- Die Zuordnung zu IMDb erfolgt automatisch. Einzelne Fehlgriffe sind möglich, deshalb lohnt ein Blick in den Bericht (`logs/report_*.md`).
