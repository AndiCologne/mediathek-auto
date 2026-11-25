# mediathek-auto

![Mediathek-Auto – ein Comic-Auto mit Filmrollen als Rädern und einem Kinositz auf dem Dach](assets/mediathek-auto.png)

Lädt automatisch gut bewertete Spielfilme aus den Mediatheken von ARD und ZDF (inklusive arte, 3sat und der Dritten Programme) herunter. Die Filme werden mit HandBrakeCLI umcodiert und als `Titel (Jahr)/Titel (Jahr).mp4` abgelegt. Nach jedem Lauf kommt auf Wunsch ein Bericht per iMessage. Läuft auf macOS und nutzt nur die Python-Standardbibliothek.

## So funktioniert es

1. Das Skript lädt die aktuelle [MediathekView](https://mediathekview.de)-Filmliste. Es ist dieselbe Liste, die auch die App MediathekView nutzt.
2. Es filtert Spielfilme heraus: ab 70 Minuten, ohne Hörfassung, Gebärdensprache, klare Sprache, Originalfassung, Krimireihen und Mehrteiler.
3. Es gleicht die Filme mit den [IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/) ab. Titel, Produktionsjahr und Laufzeit müssen passen, Dokumentarfilme werden ausgeschlossen.
4. Geladen werden Filme mit einer **IMDb-Wertung ab 8.0**, **mehr als 2.500 Stimmen** und einem **Erscheinungsjahr ab 1970**. Alle drei Grenzen sind einstellbar.
5. Die Filme werden in der besten verfügbaren Videoqualität und mit deutscher Tonspur (ohne Hörfassung) heruntergeladen und mit HandBrakeCLI umcodiert (Standard-Preset: „Apple 1080p30 Surround“).
6. Abgelegt wird als `<Zielordner>/Titel (Jahr)/Titel (Jahr).mp4`.
7. Der Film wird in `Heruntergeladene_Filme.txt` eingetragen und nie wieder geladen.

## Voraussetzungen

- macOS mit Python 3.9 oder neuer, z. B. über die Xcode Command Line Tools oder `brew install python`
- [HandBrakeCLI](https://handbrake.fr/downloads2.php), z. B. `brew install handbrake`
- `ffmpeg` und `ffprobe` (`brew install ffmpeg`): für Streams (m3u8), für die Wahl der deutschen Tonspur und für die Prüfung, ob ein Download vollständig ist

## Einrichten

```bash
git clone https://github.com/AndiCologne/mediathek-auto.git
cd mediathek-auto
cp config.example.json config.json   # Zielordner, iMessage-Adresse usw. eintragen
bash install.sh                      # wöchentlicher Lauf: Mittwoch 02:00 Uhr
```

`install.sh` richtet einen launchd-Job ein und schickt, wenn eine Adresse eingetragen ist, eine Test-iMessage. Wenn macOS fragt, ob Python „Nachrichten“ steuern darf, klickst du auf **Erlauben**.

## Aufruf von Hand

```bash
python3 mediathek_auto.py                 # normaler Lauf
python3 mediathek_auto.py --dry-run       # nur suchen, Bericht in logs/
python3 mediathek_auto.py --limit 1       # höchstens einen Film laden
python3 mediathek_auto.py --test-imessage # Test-iMessage senden
launchctl kickstart gui/$(id -u)/local.mediathek-auto   # Hintergrund-Lauf sofort starten
```

## Einstellungen (`config.json`)

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `target_dir` | `/Volumes/TB4SSD/AILocalSandbox/Movies` | Zielordner für die Filme |
| `handbrake_cli` | `/opt/homebrew/bin/HandBrakeCLI` | Pfad zu HandBrakeCLI |
| `handbrake_preset` | `Apple 1080p30 Surround` | HandBrake-Preset |
| `min_rating` | `8.0` | IMDb-Wertung mindestens |
| `min_votes` | `2500` | IMDb-Stimmen müssen mehr sein |
| `min_year` | `1970` | Erscheinungsjahr mindestens |
| `max_per_run` | `15` | Höchstzahl neuer Filme pro Lauf |
| `min_free_gb` | `30` | so viel bleibt auf dem Ziel frei |
| `imessage_to` | leer | Telefonnummer oder Apple-ID für den Bericht |
| `senders` | ARD, ZDF, arte, 3sat, Dritte … | berücksichtigte Sender |

Alle weiteren Schlüssel stehen oben in `mediathek_auto.py` unter `DEFAULTS`.

## Liste vorhandener Filme

`<Zielordner>/Heruntergeladene_Filme.txt` hat das Format `Titel (Jahr) | IMDb 8.2`. Du kannst dort auch Filme eintragen, die du schon hast. Jede Zeile wird über Titel und Jahr einem IMDb-Film zugeordnet, deshalb wird ein Film auch dann übersprungen, wenn die Mediathek ihn anders nennt. Titel, die IMDb anders schreibt, lassen sich in `state/extra_ids.json` von Hand einer IMDb-ID zuordnen (`{"tt0071562": "Der Pate - Teil II (1974)"}`).

## Ordner

- `logs/`: Protokoll und Bericht (`report_*.md`) pro Lauf
- `state/`: geladene und fehlgeschlagene Filme (nach 3 Fehlversuchen wird ein Film nicht mehr versucht)
- `cache/`: Filmliste und IMDb-Daten, etwa 1 GB, werden wöchentlich erneuert
- `tmp/`: Zwischendateien

## Wenn der nächtliche Lauf nicht auf das Laufwerk zugreifen darf

macOS kann Hintergrundprogrammen den Zugriff auf externe Laufwerke verweigern. Im Log steht dann „Operation not permitted“. Abhilfe: Systemeinstellungen → Datenschutz & Sicherheit → Festplattenvollzugriff → das Python hinzufügen, das `install.sh` anzeigt.

## Hinweise

- Die IMDb-Daten sind nur für den privaten, nicht kommerziellen Gebrauch freigegeben.
- Die Filme der Mediatheken sind für den privaten Gebrauch bestimmt. Gib sie nicht weiter.
- Die Zuordnung zu IMDb erfolgt automatisch. Einzelne Fehlgriffe sind möglich, deshalb lohnt ein Blick in den Bericht (`logs/report_*.md`).
