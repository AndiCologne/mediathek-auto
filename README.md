# mediathek-auto

![Mediathek-Auto – ein Comic-Auto mit Filmrollen als Rädern und einem Kinositz auf dem Dach](assets/mediathek-auto.png)

Lädt automatisch gut bewertete Spielfilme aus den Mediatheken von ARD und ZDF herunter, inklusive arte, 3sat und der Dritten Programme. Die Filme werden mit HandBrakeCLI umcodiert und als `Titel (Jahr)/Titel (Jahr).mp4` abgelegt. Nach jedem Lauf kommt ein Bericht per iMessage (macOS) und/oder E-Mail. Läuft auf macOS und [Windows](#windows), einmal pro Woche, und nutzt nur die Python-Standardbibliothek.

## So funktioniert es

1. Das Skript lädt die aktuelle [MediathekView](https://mediathekview.de)-Filmliste. Es ist dieselbe Liste, die auch die App MediathekView nutzt.
2. Es filtert Spielfilme heraus: passende Länge, ohne Hörfassung, Gebärdensprache, klare Sprache, Originalfassung, Krimireihen und Mehrteiler.
3. Es gleicht die Filme mit den [IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/) ab. Titel, Produktionsjahr und Laufzeit müssen passen, Dokumentarfilme werden ausgeschlossen. Gibt es mehrere Filme gleichen Titels, entscheiden die Laufzeit (±5 Minuten) und die Besetzung, siehe [Wie Filme IMDb zugeordnet werden](#wie-filme-imdb-zugeordnet-werden).
4. Geladen wird, was die Grenzen in `config.json` erfüllt. Voreingestellt sind eine IMDb-Wertung ab 8.0, mehr als 2.500 Bewertungen, Erscheinungsjahr ab 1970 und eine Länge von 70 bis 240 Minuten.
5. Filme, die schon in `Heruntergeladene_Filme.txt` stehen, werden übersprungen.
6. Heruntergeladen wird immer die beste verfügbare Videospur mit deutscher Tonspur (ohne Hörfassung). Danach prüft das Skript, ob der Download vollständig ist.
7. HandBrakeCLI codiert den Film um (Standard-Preset: „Apple 1080p30 Surround“), und die Länge wird noch einmal geprüft.
8. Der Film wird als `<Zielordner>/Titel (Jahr)/Titel (Jahr).mp4` abgelegt und in `Heruntergeladene_Filme.txt` eingetragen.
9. Zum Schluss kommt eine iMessage und/oder E-Mail mit den neuen Filmen, eventuellen Fehlern und dem freien Speicherplatz.

## Ordnerstruktur (Beispiel)

Der Code liegt in einem versteckten Unterordner des Zielordners:

```
/Volumes/TB4SSD/AILocalSandbox/Movies/        ← Zielordner (in config.json einstellbar)
├── Heruntergeladene_Filme.txt                ← Liste der vorhandenen Filme
├── Der Pate (1972)/Der Pate (1972).mp4       ← fertige Filme, je ein Ordner
├── …
└── .mediathek-auto/                          ← Code-Ordner (versteckt, im Finder: ⌘⇧.)
    ├── mediathek_auto.py                     ← das Skript
    ├── config.json                           ← alle Einstellungen
    ├── install.sh / uninstall.sh             ← wöchentlichen Zeitplan ein- und ausschalten (macOS)
    ├── install.ps1 / uninstall.ps1           ← dasselbe für Windows
    ├── README.md
    ├── cache/   Filmliste und IMDb-Daten (etwa 2 GB mit Besetzungsdaten, wöchentlich erneuert)
    ├── logs/    Protokoll und Bericht (report_*.md) je Lauf, nach 60 Tagen automatisch gelöscht
    ├── state/   interne Listen (geladene, fehlgeschlagene Filme, Zuordnungen von Hand)
    └── tmp/     Zwischendateien während eines Laufs
```

## Voraussetzungen

- macOS mit Python 3.9 oder neuer, z. B. über die Xcode Command Line Tools oder `brew install python`
- HandBrakeCLI: `brew install handbrake`
- ffmpeg und ffprobe: `brew install ffmpeg`. Gebraucht für Streams (m3u8, z. B. arte), für die Wahl der deutschen Tonspur und für die Prüfung, ob ein Download vollständig ist.

## Einrichten (Zielordner als Beispiel)

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
| `laufzeit_toleranz_minuten` | `5` | Gibt es mehrere IMDb-Filme gleichen Titels, gilt der, dessen Laufzeit höchstens so viele Minuten von der Mediathek abweicht |
| `imessage_empfaenger` | leer | Nur macOS: Telefonnummer (+49…) oder Apple-ID-E-Mail für den Bericht. Leer = keine iMessage. |
| `email_empfaenger` | leer | E-Mail-Adresse für den Bericht, mehrere mit Komma. Leer = keine E-Mail. Der Mailserver steht unter `EMAIL`. |

### EMAIL: Mailserver für den Bericht per E-Mail

| Eintrag | Voreinstellung | Bedeutung |
|---|---|---|
| `smtp_server` | leer | Postausgangsserver, z. B. `smtp.gmail.com`, `smtp.gmx.net`, `securesmtp.t-online.de` |
| `smtp_port` | `587` | Meist `587` (mit `starttls`) oder `465` (mit `ssl`) |
| `smtp_verschluesselung` | `starttls` | `starttls`, `ssl` oder `keine` |
| `smtp_benutzer` | leer | Anmeldename, meist die eigene E-Mail-Adresse |
| `smtp_passwort` | leer | Passwort bzw. App-Passwort. Alternativ leer lassen und die Umgebungsvariable `MEDIATHEK_SMTP_PASSWORT` setzen. |
| `email_absender` | leer | Absenderadresse, leer = `smtp_benutzer` |

Bei Gmail, iCloud und Outlook.com geht die Anmeldung nur mit einem App-Passwort, nicht mit dem normalen Passwort. Das Passwort steht im Klartext in `config.json`. Die Datei ist in `.gitignore` eingetragen und landet nicht auf GitHub.

### WEITERE_EINSTELLUNGEN

| Eintrag | Voreinstellung | Bedeutung |
|---|---|---|
| `filme_pro_lauf_hoechstens` | `15` | Höchstzahl neuer Filme pro Lauf |
| `freier_speicher_mindestens_gb` | `30` | So viel bleibt im Zielordner frei, sonst stoppt der Lauf |
| `besetzung_abgleichen` | `true` | Unklare Filme über Darsteller und Regie klären (lädt dafür etwa 1 GB zusätzliche IMDb-Daten pro Woche) |
| `handbrake_preset` | `Apple 1080p30 Surround` | HandBrake-Preset |
| `handbrake_programm` | `/opt/homebrew/bin/HandBrakeCLI` (Windows: `HandBrakeCLI.exe`) | Pfad zu HandBrakeCLI. Fehlt die Datei dort, wird im PATH und in `programme_ordner` gesucht. |
| `programme_ordner` | leer | Optional: Ordner mit HandBrakeCLI, ffmpeg und ffprobe, z. B. `C:\Tools` |
| `dateiendung` | `.mp4` | Dateiendung der fertigen Filme |
| `sender` | ARD, ZDF, ARTE.DE, 3Sat, Dritte … | Berücksichtigte Sender, wie sie in MediathekView heißen |
| `imessage_auch_ohne_neue_filme` | `true` | Auch dann eine iMessage bzw. E-Mail, wenn nichts Neues dabei war |
| `mac_mitteilung` | `true` | Nur macOS: zusätzlich eine Mitteilung auf dem Mac |
| `logs_aufbewahren_tage` | `60` | Ältere Logs und Berichte werden automatisch gelöscht |

Eine vollständige Vorlage steht in [`config.example.json`](config.example.json).

## Windows

Unter Windows funktioniert alles genauso wie auf dem Mac, mit drei Unterschieden:

- Der Zeitplan läuft über die **Aufgabenplanung** statt über launchd.
- Der Bericht kommt per **E-Mail**, iMessage gibt es unter Windows nicht.
- Unter Windows sind in Dateinamen bestimmte Zeichen verboten. Doppelpunkte werden deshalb zu „ -“ („Star Wars - Episode IV“), andere unerlaubte Zeichen fallen weg. Lange Titel werden gekürzt, damit der Pfad unter 260 Zeichen bleibt.

### Voraussetzungen (Windows 10/11)

- Python 3.9 oder neuer: `winget install Python.Python.3.12`
- ffmpeg und ffprobe: `winget install Gyan.FFmpeg`
- HandBrakeCLI: Die Kommandozeilen-Version gibt es auf [handbrake.fr](https://handbrake.fr/downloads2.php) als ZIP-Datei. Entpacke `HandBrakeCLI.exe` zum Beispiel nach `C:\Tools` und trage diesen Ordner in `config.json` als `programme_ordner` ein. Alternativ kannst du die Datei auch direkt in den Code-Ordner legen.
- curl ist seit Windows 10 (1803) eingebaut.
- Die SSD muss mit **exFAT** oder **NTFS** formatiert sein, denn APFS kann Windows nicht lesen. exFAT funktioniert auf Mac und Windows. Gib der SSD in der Datenträgerverwaltung einen festen Laufwerksbuchstaben, damit der Zielordner immer stimmt.

### Einrichten (Beispiel: SSD als Laufwerk `D:`)

In PowerShell, am besten mit **Als Administrator ausführen**:

```powershell
# 1. Code in den versteckten Ordner im Zielordner legen
git clone https://github.com/AndiCologne/mediathek-auto.git "D:\Movies\.mediathek-auto"
cd "D:\Movies\.mediathek-auto"

# 2. config.json anlegen und anpassen (zielordner, email_empfaenger, Abschnitt EMAIL, programme_ordner)
py -3 mediathek_auto.py --config-erstellen
notepad config.json

# 3. Wöchentlichen Zeitplan einrichten (Mittwoch 02:00 Uhr), Einrichtung prüfen, Test-E-Mail senden
powershell -ExecutionPolicy Bypass -File install.ps1
```

Ohne git kannst du den Code auch über **Code → Download ZIP** auf GitHub laden und in den Ordner entpacken. In `config.json` schreibst du Windows-Pfade mit doppeltem Backslash, zum Beispiel `"D:\\Movies"`.

`install.ps1` legt in der Aufgabenplanung die Aufgabe **Mediathek-Auto** an:

- Sie startet jeden Mittwoch um 02:00 Uhr ohne Konsolenfenster (`pythonw.exe`).
- Wurde `install.ps1` als Administrator ausgeführt, läuft sie auch, wenn niemand angemeldet ist. Ein Passwort wird dafür nicht gespeichert. Sonst läuft sie nur, wenn du angemeldet bist.
- Sie weckt den PC aus dem Energiesparmodus und holt einen verpassten Lauf nach. Dafür muss in den Energieoptionen unter „Zeitgeber zur Aktivierung zulassen“ die Einstellung **Aktivieren** gewählt sein.
- Solange ein Lauf dauert, verhindert das Skript den Energiesparmodus.

### Befehle unter Windows

```powershell
py -3 mediathek_auto.py --dry-run            # nur suchen, Bericht in logs\report_*_dryrun.md
py -3 mediathek_auto.py --limit 1            # höchstens einen Film laden
py -3 mediathek_auto.py --pruefen            # Programme, Zielordner und E-Mail prüfen
py -3 mediathek_auto.py --test-email         # Test-E-Mail senden
Start-ScheduledTask -TaskName Mediathek-Auto # Hintergrund-Lauf sofort starten
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -like '*mediathek_auto*' | Invoke-CimMethod -MethodName Terminate   # laufenden Durchgang abbrechen
powershell -ExecutionPolicy Bypass -File uninstall.ps1   # Zeitplan entfernen
```

## Wie Filme IMDb zugeordnet werden

Die Mediathek liefert Titel, Länge, eine Beschreibung und einen Link zur Sendungsseite. Ein Produktionsjahr steht nur manchmal dabei. Bei 3sat steht es meist im Titel („Spielfilm, USA 1972“), bei ARD und arte oft nicht. Bei IMDb gibt es dagegen für viele Titel mehrere Filme: Remakes („Papillon“ von 1973 und 2017), Neuverfilmungen von Märchen oder Allerweltstitel wie „Luther“. Damit nie der falsche Film mit der falschen Wertung geladen wird, prüft das Skript in dieser Reihenfolge:

1. **Titel:** Der deutsche Mediathek-Titel wird mit den IMDb-Titeln verglichen, auch mit den deutschen Verleihtiteln.
2. **Produktionsjahr:** Steht ein Jahr in Titel oder Beschreibung, muss das IMDb-Jahr auf ±1 Jahr passen.
3. **Laufzeit:** Bleibt mehr als ein Kandidat übrig, gilt der, dessen IMDb-Laufzeit höchstens `laufzeit_toleranz_minuten` (Standard 5) von der Mediathek abweicht. Berücksichtigt ist, dass Filme im deutschen Fernsehen rund 4 % kürzer laufen (25 statt 24 Bilder pro Sekunde): Ein 120-Minuten-Film dauert dort 115 Minuten.
4. **Bekanntheit:** Hat ein Kandidat mindestens fünfmal so viele IMDb-Bewertungen wie der nächste, ist er es.
5. **Besetzung:** Ist es danach noch unklar, ruft das Skript die Sendungsseite aus dem Mediathek-Link ab. Dort und in der Beschreibung sucht es nach den Namen von Darstellern und Regie der IMDb-Kandidaten. Es gewinnt der Kandidat mit den meisten Treffern, wenn er eindeutig vorne liegt.
   Auch Filme ohne Jahresangabe, die bei IMDb wenig bekannt sind, werden so geprüft: Sie werden nur geladen, wenn mindestens zwei Namen aus ihrer Besetzung gefunden werden.

Der Besetzungs-Abgleich läuft nur für Filme, bei denen mindestens ein Kandidat die Kriterien erfüllen würde (Wertung, Bewertungen, Jahr). Dafür lädt das Skript die IMDb-Datensätze `title.principals` und `name.basics` (zusammen etwa 1 GB, wöchentlich zwischengespeichert).

Der Bericht `logs/report_*.md` zeigt, was passiert ist:
- **Über die Besetzung zugeordnet:** Filme, die erst über Darsteller oder Regie geklärt wurden, mit den gefundenen Namen
- **Nicht eindeutig zuzuordnen, übersprungen:** Titel, die trotz allem unklar bleiben. Hier stehen nur Fälle, bei denen mindestens ein Kandidat die Kriterien erfüllen würde, du verpasst also nichts anderes.

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
python3 mediathek_auto.py --test-email       # Test-E-Mail senden
python3 mediathek_auto.py --pruefen          # Programme, Zielordner und Benachrichtigung prüfen
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
