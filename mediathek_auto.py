#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mediathek_auto.py – Spielfilme aus den ARD/ZDF-Mediatheken mit IMDb-Wertung ab 8.0, erschienen ab 1970
finden, herunterladen, mit HandBrakeCLI umcodieren und als
"<Ziel>/Titel (Jahr)/Titel (Jahr).mp4" ablegen.

Datenquellen:
  * MediathekView-Filmliste (dieselbe Liste, die die App MediathekView nutzt)
  * IMDb Non-Commercial Datasets (https://developer.imdb.com/non-commercial-datasets/)

Aufruf:
  python3 mediathek_auto.py              # normaler Lauf
  python3 mediathek_auto.py --dry-run    # nur suchen + Bericht, nichts laden
  python3 mediathek_auto.py --limit 2    # höchstens 2 Filme in diesem Lauf

Nur Python-Standardbibliothek (läuft mit dem macOS-Python 3.9+).
"""

import argparse
import datetime as dt
import fcntl
import gzip
import json
import logging
import lzma
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Konfiguration (kann über config.json im selben Ordner überschrieben werden)
# --------------------------------------------------------------------------
DEFAULTS = {
    "target_dir": "/Volumes/TB4SSD/AILocalSandbox/Movies",
    "handbrake_cli": "/opt/homebrew/bin/HandBrakeCLI",
    "handbrake_preset": "Apple 1080p30 Surround",
    "file_extension": ".mp4",
    "min_rating": 8.0,            # Wertung mindestens so hoch (ab 8.0)
    "min_year": 1970,             # Erscheinungsjahr laut IMDb mindestens
    "min_votes": 2500,            # IMDb-Stimmen müssen MEHR als dieser Wert sein
    "min_minutes": 70,            # Mindestlänge in der Mediathek
    "max_minutes": 240,           # Höchstlänge in der Mediathek (0 = keine Grenze)
    "runtime_tolerance": 5,       # Laufzeit Mediathek vs. IMDb, ± Minuten (entscheidet bei Mehrdeutigkeit)
    "cast_check": True,           # mehrdeutige/unsichere Filme über die Besetzung klären
    "max_per_run": 15,            # Höchstzahl neuer Filme pro Lauf
    "min_free_gb": 30,            # so viel muss auf der SSD frei bleiben
    "imdb_types": ["movie", "tvMovie"],
    "exclude_genres": ["Documentary"],
    "imdb_max_age_days": 6,       # IMDb-Daten nur neu laden, wenn älter
    "senders": [
        "ARD", "ZDF", "ARTE.DE", "3Sat", "BR", "HR", "MDR", "NDR", "RBB", "SR",
        "SWR", "WDR", "Radio Bremen TV", "ONE", "ARD-alpha", "tagesschau24",
        "PHOENIX", "KiKA", "ZDF-tivi", "ZDFneo", "ZDFinfo",
    ],
    "filmlist_urls": [
        "https://liste.mediathekview.de/Filmliste-akt.xz",
        "https://verteiler1.mediathekview.de/Filmliste-akt.xz",
        "https://verteiler2.mediathekview.de/Filmliste-akt.xz",
        "https://verteiler3.mediathekview.de/Filmliste-akt.xz",
    ],
    "imdb_base_url": "https://datasets.imdbws.com/",
    "notify": True,               # macOS-Mitteilung am Ende
    "imessage_to": "",            # Telefonnummer oder Apple-ID-E-Mail für den Abschlussbericht
    "imessage_when_nothing_new": True,  # auch melden, wenn nichts Neues dabei war
    "list_file": "",              # leer = <target_dir>/Heruntergeladene_Filme.txt
    "log_keep_days": 60,          # ältere Logs/Berichte werden automatisch gelöscht
}

# Beschriftete Einträge der config.json -> interne Namen.
# Reihenfolge und Texte bestimmen auch, wie --config-erstellen die Datei schreibt.
CONFIG_SCHEMA = [
    ("ANPASSBAR", [
        ("zielordner", "target_dir",
         "Ordner für die fertigen Filme (je Film ein Unterordner 'Titel (Jahr)'). Hier liegt auch Heruntergeladene_Filme.txt."),
        ("imdb_wertung_mindestens", "min_rating",
         "Nur Filme mit dieser IMDb-Wertung oder höher, z. B. 8.0."),
        ("imdb_bewertungen_mehr_als", "min_votes",
         "Der Film braucht MEHR IMDb-Bewertungen als diese Zahl (filtert unbekannte Filme mit Zufallswertung)."),
        ("laenge_mindestens_minuten", "min_minutes",
         "Kürzere Sendungen werden ignoriert (Spielfilme dauern meist ab 80 Minuten)."),
        ("laenge_hoechstens_minuten", "max_minutes",
         "Längere Sendungen werden ignoriert. 0 = keine Obergrenze."),
        ("erscheinungsjahr_ab", "min_year",
         "Nur Filme, die laut IMDb in diesem Jahr oder später erschienen sind. 0 = alle Jahre."),
        ("laufzeit_toleranz_minuten", "runtime_tolerance",
         "Gibt es bei IMDb mehrere Filme gleichen Titels, gilt der, dessen Laufzeit höchstens so viele "
         "Minuten von der Mediathek abweicht (TV-Fassungen laufen ca. 4 % kürzer, das ist berücksichtigt)."),
        ("imessage_empfaenger", "imessage_to",
         "Telefonnummer (+49…) oder Apple-ID-E-Mail für den Bericht nach jedem Lauf. Leer = keine iMessage."),
    ]),
    ("WEITERE_EINSTELLUNGEN", [
        ("filme_pro_lauf_hoechstens", "max_per_run",
         "So viele neue Filme werden pro Lauf höchstens geladen (ein Film braucht ca. 30–60 Minuten)."),
        ("freier_speicher_mindestens_gb", "min_free_gb",
         "So viel Platz bleibt im Zielordner mindestens frei, sonst stoppt der Lauf."),
        ("besetzung_abgleichen", "cast_check",
         "true = mehrdeutige Filme über Darsteller/Regie klären (Mediathek-Seite + IMDb-Besetzung, "
         "lädt dafür ca. 1 GB IMDb-Daten wöchentlich)."),
        ("handbrake_preset", "handbrake_preset",
         "Name des HandBrake-Presets für das Umcodieren."),
        ("handbrake_programm", "handbrake_cli",
         "Pfad zu HandBrakeCLI."),
        ("dateiendung", "file_extension",
         "Dateiendung der fertigen Filme."),
        ("sender", "senders",
         "Berücksichtigte Sender, so wie sie in MediathekView heißen."),
        ("imessage_auch_ohne_neue_filme", "imessage_when_nothing_new",
         "true = auch dann eine iMessage, wenn kein neuer Film dabei war."),
        ("mac_mitteilung", "notify",
         "true = zusätzlich eine Mitteilung auf dem Mac anzeigen."),
        ("logs_aufbewahren_tage", "log_keep_days",
         "Logs und Berichte, die älter sind, werden automatisch gelöscht."),
    ]),
]
CONFIG_NOTE = ("Einstellungen für Mediathek-Auto. Nur die Werte hinter \"wert\" ändern, "
               "die \"info\"-Texte erklären den Eintrag. Zahlen ohne Anführungszeichen, "
               "Dezimalpunkt statt Komma (8.0). Gilt ab dem nächsten Lauf.")

WORK_DIR = BASE_DIR
STATE_DIR = os.path.join(WORK_DIR, "state")
LOG_DIR = os.path.join(WORK_DIR, "logs")
CACHE_DIR = os.path.join(WORK_DIR, "cache")
TMP_DIR = os.path.join(WORK_DIR, "tmp")

EXCLUDE_MARKERS = [
    "audiodeskription", "hörfassung", "hoerfassung", "hörfilm", "gebärdensprache",
    "gebaerdensprache", "klare sprache", "klarer sprache", "(ov)", "omu", "originalversion",
    "originalfassung", "originalton", "(englisch", "(französisch", "(italienisch", "(spanisch",
    "(original", "trailer", "making of", "making-of", "teaser", "vorschau",
]
EXCLUDE_THEMES = ["tatort", "polizeiruf", "soko ", "der alte", "rosenheim-cops", "ein starkes team",
                  "wilsberg", "nord bei nordwest", "der staatsanwalt", "die chefin"]
FILM_SIGNAL_THEMA = re.compile(
    r"(spielfilm|fernsehfilm|kinofilm|\bfilm|\bfilme\b|kino|movie|thriller|komödie|"
    r"krimi|drama|western|filmmittwoch|filmdebüt|filmfreitag|filmsonntag)",
    re.IGNORECASE)
FILM_SIGNAL_DESC = re.compile(
    r"(spielfilm|fernsehfilm|kinofilm|tv-film|regie:|regie |darsteller|mit [A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ])",
    re.IGNORECASE)
TITLE_JUNK = re.compile(
    r"\b(spielfilm|fernsehfilm|kinofilm|mit untertitel|untertitel)\b\s*$",
    re.IGNORECASE)
YEAR_RE = re.compile(r"(?<!\d)(19[1-9]\d|20[0-4]\d)(?!\d)")
COUNTRIES = (
    r"Deutschland|BRD|DDR|USA|Frankreich|Großbritannien|GB|England|Italien|Spanien|Österreich|"
    r"Schweiz|Kanada|Japan|Südkorea|Korea|China|Hongkong|Taiwan|Dänemark|Schweden|Norwegen|"
    r"Finnland|Island|Polen|Tschechien|Tschechoslowakei|Slowakei|Ungarn|Rumänien|Bulgarien|"
    r"Belgien|Niederlande|Luxemburg|Irland|Australien|Neuseeland|Argentinien|Brasilien|Mexiko|"
    r"Chile|Kolumbien|Peru|Indien|Iran|Israel|Türkei|Russland|Sowjetunion|UdSSR|Griechenland|"
    r"Portugal|Südafrika|Libanon|Ägypten|Marokko|Tunesien|Kroatien|Serbien|Jugoslawien|"
    r"Ukraine|Georgien|Estland|Lettland|Litauen|Slowenien|Bosnien(?:-Herzegowina)?|Thailand|"
    r"Indonesien|Philippinen|Senegal|Algerien|Kuba|Uruguay|Venezuela|Bolivien|Paraguay|"
    r"Mongolei|Kasachstan|Vietnam|Pakistan|Jordanien|Palästina|Syrien|Irak|Saudi-Arabien")
# "USA 1972", "BRD/Italien/Spanien 1965", "Frankreich, 2019", "USA 1979/2019"
PROD_YEAR_RE = re.compile(
    r"(?:\b(?:%s))(?:\s*[/,]\s*(?:%s))*\s*,?\s+(19[1-9]\d|20[0-4]\d)(?:\s*/\s*(19[1-9]\d|20[0-4]\d))?"
    % (COUNTRIES, COUNTRIES))
# " - Spielfilm, USA 1972" bzw. ", USA 1972" am Titelende
TITLE_TAIL = re.compile(
    r"(\s*[-–—|,:]\s*(spielfilm|fernsehfilm|kinofilm|film)\b.*$)|"
    r"(\s*[-–—|,:]?\s*(?:%s)(?:\s*[/,]\s*(?:%s))*\s*,?\s+(19|20)\d\d(\s*/\s*(19|20)\d\d)?\s*$)"
    % (COUNTRIES, COUNTRIES), re.IGNORECASE)
EPISODE_RE = re.compile(r"\(S\d+\s*/\s*E\d+\)|\bFolge\s+\d+|\(\d+\s*/\s*\d+\)|schicksalsjahre", re.IGNORECASE)
# 3sat: "..._mit_ad_..._a1a2_..." = normale Fassung, "_a3a4_" = Hörfassung
AD_URL_RE = re.compile(r"(_a3a4_|audiodeskription|hoerfassung|_dgs[_\.]|gebaerden)", re.IGNORECASE)

log = logging.getLogger("mediathek_auto")


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
def load_config() -> dict:
    """Liest config.json. Versteht das beschriftete Format (ANPASSBAR/WEITERE_EINSTELLUNGEN
    mit "wert"/"info") und – für ältere Installationen – flache interne Schlüssel."""
    cfg = dict(DEFAULTS)
    path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(path):
        return cfg
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    labels = {label: key for _, items in CONFIG_SCHEMA for label, key, _ in items}
    for name, val in raw.items():
        if name.startswith("_"):
            continue
        if isinstance(val, dict) and name in {sec for sec, _ in CONFIG_SCHEMA}:
            for label, entry in val.items():
                v = entry.get("wert") if isinstance(entry, dict) else entry
                if label in labels:
                    cfg[labels[label]] = v
                elif label in DEFAULTS:
                    cfg[label] = v
                else:
                    print("Hinweis: unbekannter Eintrag in config.json: %s" % label, file=sys.stderr)
        elif name in DEFAULTS:
            cfg[name] = val
        elif name in labels:
            cfg[labels[name]] = val.get("wert") if isinstance(val, dict) else val
    return cfg


def config_document(cfg: dict) -> dict:
    """Beschriftete config.json aus den aktuellen Einstellungen."""
    doc: Dict[str, object] = {"_LIESMICH": CONFIG_NOTE}
    for sec, items in CONFIG_SCHEMA:
        doc[sec] = {label: {"wert": cfg.get(key), "info": info} for label, key, info in items}
    return doc


def norm(s: str) -> str:
    """Titel vergleichbar machen: klein, ohne Akzente/Umlautpunkte, nur a-z0-9."""
    s = s.casefold().replace("ß", "ss").replace("&", " und ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def clean_title(title: str) -> str:
    """'Der Pate - Spielfilm, USA 1972 (mit Untertitel)' -> 'Der Pate'."""
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", title).strip()
    for _ in range(2):
        t = TITLE_TAIL.sub("", t).strip()
        t = TITLE_JUNK.sub("", t).strip(" -–—|:,.\"'„“")
    return t


def title_variants(title: str) -> List[str]:
    """Mögliche 'echte' Filmtitel. Element 0 ist immer der bereinigte Haupttitel."""
    out: List[str] = []

    def add(t: str):
        t = t.strip(" -–—|:,.\"'„“")
        t = TITLE_JUNK.sub("", t).strip(" -–—|:,.")
        n = norm(t)
        # Teilstücke ohne Buchstaben (z. B. "1990") sind keine Filmtitel
        if len(n) >= 2 and re.search(r"[a-z]", n) and t not in out:
            out.append(t)

    base = clean_title(title)
    add(base)
    if not out:
        return out
    add(re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", title))
    for sep in [" - ", " – ", " — ", " | ", ": "]:
        if sep in base:
            parts = [p for p in base.split(sep) if p.strip()]
            if parts:
                add(parts[0])
                add(parts[-1])
                if len(parts) > 2:
                    add(sep.join(parts[1:]))
    return out


def safe_name(s: str) -> str:
    s = s.replace("/", " - ").replace(":", " -").replace("\\", " ")
    s = re.sub(r"[\x00-\x1f\"*?<>|]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:150] or "Unbenannt"


def duration_min(d: str) -> Optional[float]:
    try:
        parts = [int(x) for x in d.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, s = parts[-3:]
        return h * 60 + m + s / 60.0
    except Exception:
        return None


def expand_url(base: str, value: str) -> str:
    """MediathekView speichert Url Klein/HD als 'N|rest' = base[:N] + rest."""
    if not value:
        return ""
    if "|" in value:
        n, rest = value.split("|", 1)
        if n.isdigit():
            return base[: int(n)] + rest
    return value


def run(cmd: List[str], **kw) -> int:
    log.debug("RUN %s", " ".join(cmd))
    return subprocess.call(cmd, **kw)


def curl_download(url: str, dest: str, quiet: bool = True) -> bool:
    tmp = dest + ".part"
    cmd = ["curl", "-L", "--fail", "--retry", "3", "--retry-delay", "10",
           "--connect-timeout", "30", "-C", "-", "-o", tmp, url]
    if quiet:
        cmd.insert(1, "-sS")
    rc = run(cmd)
    if rc != 0:
        log.warning("Download fehlgeschlagen (curl rc=%s): %s", rc, url)
        return False
    os.replace(tmp, dest)
    return True


def file_age_days(path: str) -> float:
    if not os.path.exists(path):
        return 1e9
    return (time.time() - os.path.getmtime(path)) / 86400.0


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


IMESSAGE_SCRIPT = '''
on run argv
  set theText to item 1 of argv
  set theTo to item 2 of argv
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    try
      send theText to participant theTo of svc
    on error
      send theText to buddy theTo of svc
    end try
  end tell
end run
'''


def send_imessage(cfg: dict, text: str) -> bool:
    to = (cfg.get("imessage_to") or "").strip()
    if not to:
        log.info("Keine iMessage-Adresse eingetragen (config.json → imessage_to).")
        return False
    try:
        p = subprocess.run(["osascript", "-e", IMESSAGE_SCRIPT, text, to],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            log.warning("iMessage fehlgeschlagen: %s", p.stderr.strip())
            return False
        log.info("iMessage an %s gesendet.", to)
        return True
    except Exception as ex:  # noqa
        log.warning("iMessage fehlgeschlagen: %s", ex)
        return False


# --------------------------------------------------------------------------
# Textliste der geladenen Filme (auch von Hand ergänzbar)
# --------------------------------------------------------------------------
LIST_HEADER = (
    "# Filme, die schon vorhanden sind – sie werden nicht noch einmal geladen.\n"
    "# Format: Titel (Jahr) | IMDb-Wertung\n"
    "# Eigene Zeilen sind erlaubt, z. B. 'Titel (Jahr)' oder nur 'Titel'.\n"
)
LIST_YEAR_RE = re.compile(r"^(.*?)\s*\((19\d\d|20\d\d)\)\s*$")


def list_path(cfg: dict) -> str:
    return cfg.get("list_file") or os.path.join(cfg["target_dir"], "Heruntergeladene_Filme.txt")


def list_line(name: str, rating) -> str:
    return "%s | %s" % (name, ("IMDb %.1f" % rating) if rating else "IMDb ?")


def read_list(path: str):
    """Liefert (IMDb-IDs, normalisierte Namen, [(Titel, Jahr|None)])."""
    ids: Set[str] = set()
    names: Set[str] = set()
    entries: List[Tuple[str, Optional[int]]] = []
    if not os.path.exists(path):
        return ids, names, entries
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ids.update(re.findall(r"\btt\d{6,}\b", line))
            first = line.split("|")[0].strip()
            if not first or re.fullmatch(r"tt\d{6,}", first):
                continue
            names.add(norm(first))
            m = LIST_YEAR_RE.match(first)
            if m:
                names.add(norm(m.group(1)) + " " + m.group(2))
                entries.append((m.group(1).strip(), int(m.group(2))))
            else:
                entries.append((first, None))
    return ids, names, entries


def _list_variants(t: str) -> List[str]:
    """Wie title_variants, aber auch reine Zahlentitel ('2012') zulassen."""
    v = title_variants(t)
    if norm(t) and t not in v:
        v.insert(0, t)
    return v


def list_wanted(entries) -> Set[str]:
    return {norm(v) for t, _ in entries for v in _list_variants(t)}


def resolve_list_ids(entries, by_title, info) -> Dict[str, Tuple[str, Optional[int]]]:
    """Ordnet Listeneinträge IMDb-IDs zu. Vollständiger Titel vor Teilstücken,
    exaktes Jahr vor ±1, bei Gleichstand der bekannteste Film."""
    out: Dict[str, Tuple[str, Optional[int]]] = {}
    for t, y in entries:
        best = None
        for v in _list_variants(t):
            c = [info[x] for x in by_title.get(norm(v), ()) if x in info]
            if y:
                exact = [m for m in c if m["year"] == y]
                c = exact or [m for m in c if m["year"] and abs(m["year"] - y) <= 1]
            if c:
                best = max(c, key=lambda m: m.get("votes", 0))
                break
        if best:
            out[best["id"]] = (t, y)
    return out


def ensure_list(cfg: dict, done: dict) -> None:
    """Legt die Liste an bzw. ergänzt geladene Filme aus done.json, die darin fehlen."""
    path = list_path(cfg)
    _, names, _ = read_list(path)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(LIST_HEADER)
    missing = [r for r in done.values() if norm(r.get("name", "")) not in names]
    if missing:
        with open(path, "a", encoding="utf-8") as f:
            for r in missing:
                f.write(list_line(r.get("name", "?"), r.get("rating")) + "\n")


def append_list(cfg: dict, rec: dict, tid: str) -> None:
    with open(list_path(cfg), "a", encoding="utf-8") as f:
        f.write(list_line(rec.get("name", "?"), rec.get("rating")) + "\n")


def notify(title: str, text: str) -> None:
    try:
        text = text.replace('"', "'")
        subprocess.call(["osascript", "-e",
                         'display notification "%s" with title "%s"' % (text, title)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Filmliste
# --------------------------------------------------------------------------
STD_COLS = ["Sender", "Thema", "Titel", "Datum", "Zeit", "Dauer", "Größe [MB]",
            "Beschreibung", "Url", "Website", "Url Untertitel", "Url RTMP",
            "Url Klein", "Url RTMP Klein", "Url HD", "Url RTMP HD", "DatumL",
            "Url History", "Geo", "neu"]


def fetch_filmlist(cfg: dict) -> str:
    dest = os.path.join(CACHE_DIR, "Filmliste-akt.xz")
    for url in cfg["filmlist_urls"]:
        log.info("Lade Filmliste von %s", url)
        if curl_download(url, dest):
            return dest
    if os.path.exists(dest) and file_age_days(dest) < 3:
        log.warning("Nutze zwischengespeicherte Filmliste.")
        return dest
    raise RuntimeError("Filmliste konnte nicht geladen werden.")


def iter_filmlist(text: str):
    """Liefert Dicts pro Film. Leere Sender/Thema-Felder erben vom Vorgänger."""
    dec = json.JSONDecoder()
    cols = STD_COLS
    # Kopfzeilen: zweites "Filmliste"-Array enthält die Spaltennamen
    pos = [m.end() for m in re.finditer(r'"Filmliste"\s*:\s*', text[:20000])]
    if len(pos) >= 2:
        try:
            hdr, _ = dec.raw_decode(text, pos[1])
            if isinstance(hdr, list) and "Titel" in hdr:
                cols = hdr
        except ValueError:
            pass
    idx = {name: i for i, name in enumerate(cols)}
    last_sender, last_thema = "", ""
    key = re.compile(r'"X"\s*:\s*')
    i = 0
    while True:
        m = key.search(text, i)
        if not m:
            break
        try:
            row, i = dec.raw_decode(text, m.end())
        except ValueError:
            i = m.end()
            continue

        def g(name: str) -> str:
            j = idx.get(name)
            return row[j] if j is not None and j < len(row) else ""

        sender = g("Sender") or last_sender
        thema = g("Thema") or last_thema
        last_sender, last_thema = sender, thema
        url = g("Url")
        yield {
            "sender": sender, "thema": thema, "titel": g("Titel"),
            "datum": g("Datum"), "dauer": g("Dauer"), "groesse": g("Größe [MB]"),
            "beschreibung": g("Beschreibung"), "url": url,
            "url_hd": expand_url(url, g("Url HD")), "website": g("Website"),
            "geo": g("Geo"),
        }


def select_candidates(cfg: dict, path: str) -> List[dict]:
    senders = {s.casefold() for s in cfg["senders"]}
    with lzma.open(path, "rt", encoding="utf-8") as f:
        text = f.read()
    total, cands = 0, []
    for e in iter_filmlist(text):
        total += 1
        if e["sender"].casefold() not in senders:
            continue
        mins = duration_min(e["dauer"])
        if mins is None or mins < cfg["min_minutes"]:
            continue
        if cfg.get("max_minutes") and mins > cfg["max_minutes"]:
            continue
        if not (e["url"] or e["url_hd"]):
            continue
        if e["geo"] and "DE" not in e["geo"].upper():
            continue
        low = (e["titel"] + " " + e["thema"]).casefold()
        if any(mk in low for mk in EXCLUDE_MARKERS) or EPISODE_RE.search(e["titel"]):
            continue
        if any(e["thema"].casefold().startswith(t) for t in EXCLUDE_THEMES):
            continue
        # Hörfassung/Gebärdensprache erkennt man oft nur an der Adresse
        if AD_URL_RE.search(e["url_hd"] or e["url"]):
            if e["url"] and not AD_URL_RE.search(e["url"]):
                e["url_hd"] = ""
            else:
                continue
        txt = e["titel"] + " " + e["beschreibung"]
        prod = set()
        for a, b in PROD_YEAR_RE.findall(txt):
            prod.add(int(a))
            if b:
                prod.add(int(b))
        e["prod_years"] = sorted(prod)
        years = sorted({int(y) for y in YEAR_RE.findall(txt)})
        signal = bool(FILM_SIGNAL_THEMA.search(e["thema"]) or FILM_SIGNAL_THEMA.search(e["titel"])
                      or FILM_SIGNAL_DESC.search(e["beschreibung"]))
        if not (signal or years):
            continue
        e["minutes"] = mins
        e["years"] = years
        e["signal"] = signal
        e["variants"] = title_variants(e["titel"])
        if e["variants"]:
            cands.append(e)
    del text
    log.info("Filmliste: %d Einträge, %d mögliche Spielfilme.", total, len(cands))
    return cands


# --------------------------------------------------------------------------
# IMDb
# --------------------------------------------------------------------------
def fetch_imdb(cfg: dict) -> Dict[str, str]:
    files = {}
    for name in ["title.akas.tsv.gz", "title.basics.tsv.gz", "title.ratings.tsv.gz"]:
        dest = os.path.join(CACHE_DIR, name)
        if file_age_days(dest) > cfg["imdb_max_age_days"]:
            log.info("Lade IMDb-Datensatz %s", name)
            if not curl_download(cfg["imdb_base_url"] + name, dest) and not os.path.exists(dest):
                raise RuntimeError("IMDb-Datensatz %s nicht verfügbar." % name)
        files[name] = dest
    return files


def iter_tsv(path: str):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        f.readline()  # Kopfzeile
        for line in f:
            yield line.rstrip("\n").split("\t")


def build_imdb_index(cfg: dict, files: Dict[str, str], wanted: Set[str]):
    """Nur Titel indizieren, die in der Mediathek vorkommen (spart Speicher)."""
    types = set(cfg["imdb_types"])
    by_title: Dict[str, Set[str]] = {}
    for row in iter_tsv(files["title.akas.tsv.gz"]):
        if len(row) < 4:
            continue
        n = norm(row[2])
        if n in wanted:
            by_title.setdefault(n, set()).add(row[0])
    aka_ids = set().union(*by_title.values()) if by_title else set()
    log.info("IMDb akas: %d passende Titel-IDs.", len(aka_ids))

    info: Dict[str, dict] = {}
    for row in iter_tsv(files["title.basics.tsv.gz"]):
        if len(row) < 9 or row[1] not in types or row[4] == "1":
            continue
        tid = row[0]
        np, no = norm(row[2]), norm(row[3])
        hit = tid in aka_ids or np in wanted or no in wanted
        if not hit:
            continue
        for n in (np, no):
            if n in wanted:
                by_title.setdefault(n, set()).add(tid)
        info[tid] = {
            "id": tid, "type": row[1], "title": row[2], "original": row[3],
            "year": int(row[5]) if row[5].isdigit() else None,
            "runtime": int(row[7]) if row[7].isdigit() else None,
            "genres": [] if row[8] == "\\N" else row[8].split(","),
        }
    for row in iter_tsv(files["title.ratings.tsv.gz"]):
        if len(row) >= 3 and row[0] in info:
            info[row[0]]["rating"] = float(row[1])
            info[row[0]]["votes"] = int(row[2])
    log.info("IMDb: %d passende Filme mit Metadaten.", len(info))
    return by_title, info


def match_entry(cfg: dict, e: dict, by_title, info) -> Tuple[Optional[dict], str]:
    """Regeln:
    * Produktionsjahr erkannt ("USA 1972"): IMDb-Jahr muss ±1 passen; Teil-Titel erlaubt.
    * sonst: nur der vollständige, bereinigte Titel zählt (keine Teilstücke wie
      'Winterlicht' aus 'Winterlicht - Der Usedom-Krimi'), plus Jahr/Film-Hinweis.
    """
    excl = set(cfg["exclude_genres"])
    primary = norm(e["variants"][0])
    prod = e.get("prod_years") or []
    hits: Dict[str, str] = {}  # tid -> Variante, über die gefunden
    for v in e["variants"]:
        n = norm(v)
        if not prod and n != primary:
            continue
        for tid in by_title.get(n, ()):
            if tid in info and (tid not in hits or n == primary):
                hits[tid] = v
    c = [info[t] for t in hits if not (set(info[t]["genres"]) & excl)]
    if not c:
        return None, "kein IMDb-Treffer"
    if prod:
        c = [m for m in c if m["year"] and any(abs(m["year"] - y) <= 1 for y in prod)]
        if not c:
            return None, "Jahr passt nicht"
    elif e["years"]:
        c = [m for m in c if m["year"] and any(abs(m["year"] - y) <= 1 for y in e["years"])]
        if not c:
            return None, "Jahr passt nicht"
    elif not e["signal"]:
        return None, "kein Jahr, kein Film-Hinweis"
    mins = e["minutes"]
    c = [m for m in c if not m["runtime"] or abs(m["runtime"] - mins) <= max(12, 0.2 * m["runtime"])]
    if not c:
        return None, "Laufzeit passt nicht"
    if len(c) > 1:
        exact = [m for m in c if norm(hits[m["id"]]) == primary]
        if exact:
            c = exact
    if len(c) > 1:
        # Laufzeit mit Toleranz: bleibt genau ein Kandidat, ist er es
        tol = float(cfg.get("runtime_tolerance") or 0)
        close = [m for m in c if runtime_close(m.get("runtime"), mins, tol)]
        if len(close) == 1:
            c = close
        elif len(close) > 1:
            c = close
    c = [dict(m, _via=hits[m["id"]]) for m in c]   # Kopien, info[] bleibt unverändert
    if len(c) > 1:
        c.sort(key=lambda m: m.get("votes", 0), reverse=True)
        if c[0].get("votes", 0) >= 5 * max(1, c[1].get("votes", 0)):
            c = c[:1]
        else:
            e["_cands"] = c
            return None, "mehrdeutig: " + ", ".join("%s (%s)" % (m["title"], m["year"]) for m in c[:4])
    if not prod and not e["years"] and c[0].get("votes", 0) < 5 * cfg["min_votes"]:
        e["_cands"] = c
        return None, "unsicher (kein Jahr, wenig bekannt)"
    return c[0], "ok"


def runtime_close(rt: Optional[int], mins: float, tol: float) -> bool:
    """IMDb-Laufzeit passt auf ±tol Minuten – auch zur TV-Fassung (25 statt 24 Bilder/s, ca. 4 % kürzer)."""
    if not rt or not tol:
        return False
    return abs(mins - rt) <= tol or abs(mins - rt * 24.0 / 25.0) <= tol


def qualifies(cfg: dict, m: dict) -> bool:
    """Erfüllt der IMDb-Film die Auswahlkriterien (Wertung, Stimmen, Jahr)?"""
    return (m.get("rating", 0) >= cfg["min_rating"] and m.get("votes", 0) > cfg["min_votes"]
            and (m.get("year") or 0) >= (cfg.get("min_year") or 0))


# --------------------------------------------------------------------------
# Besetzungs-Abgleich (IMDb principals + name.basics vs. Mediathek-Seite)
# --------------------------------------------------------------------------
CAST_FILES = ["title.principals.tsv.gz", "name.basics.tsv.gz"]
CAST_CATEGORIES = {"actor", "actress", "director", "self"}


def load_cast(cfg: dict, tids: Set[str]) -> Dict[str, List[str]]:
    """IMDb-ID -> Namen von Darstellern und Regie (nur für die gefragten Filme)."""
    files = {}
    for name in CAST_FILES:
        dest = os.path.join(CACHE_DIR, name)
        if file_age_days(dest) > cfg["imdb_max_age_days"]:
            log.info("Lade IMDb-Datensatz %s (für den Besetzungs-Abgleich)", name)
            if not curl_download(cfg["imdb_base_url"] + name, dest) and not os.path.exists(dest):
                log.warning("Besetzungs-Abgleich nicht möglich: %s fehlt.", name)
                return {}
        files[name] = dest
    people: Dict[str, List[str]] = {}
    nconsts: Set[str] = set()
    for row in iter_tsv(files["title.principals.tsv.gz"]):
        if len(row) >= 4 and row[0] in tids and row[3] in CAST_CATEGORIES:
            people.setdefault(row[0], []).append(row[2])
            nconsts.add(row[2])
    names: Dict[str, str] = {}
    for row in iter_tsv(files["name.basics.tsv.gz"]):
        if len(row) >= 2 and row[0] in nconsts:
            names[row[0]] = row[1]
    return {t: [names[n] for n in ns if n in names] for t, ns in people.items()}


def page_text(url: str) -> str:
    """Text der Sendungsseite (HTML ohne Tags, Entities/Unicode-Escapes aufgelöst)."""
    if not url or not url.startswith("http"):
        return ""
    try:
        raw = subprocess.run(["curl", "-sS", "-L", "--fail", "--max-time", "25", "-A",
                              "Mozilla/5.0 (Macintosh) mediathek-auto", url],
                             capture_output=True, timeout=40).stdout.decode("utf-8", "replace")
    except Exception:
        return ""
    import html as _html
    raw = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return _html.unescape(raw)


def cast_hits(names: List[str], text_norm: str) -> List[str]:
    found = []
    for n in names:
        nn = norm(n)
        if len(nn) >= 5 and " " in nn and (" " + nn + " ") in text_norm:
            found.append(n)
    return found


def resolve_by_cast(cfg: dict, entries: List[dict]) -> Dict[int, Tuple[dict, List[str]]]:
    """Klärt mehrdeutige/unsichere Einträge über die Besetzung.
    Mehrdeutig: Kandidat mit den meisten Treffern (mind. 1, eindeutig vorne).
    Unsicher (ein Kandidat): mind. 2 Namen müssen auf der Seite stehen."""
    tids = {m["id"] for e in entries for m in e["_cands"]}
    if not tids:
        return {}
    cast = load_cast(cfg, tids)
    if not cast:
        return {}
    out: Dict[int, Tuple[dict, List[str]]] = {}
    pages: Dict[str, str] = {}
    for e in entries:
        site = e.get("website", "")
        if site and site not in pages:
            pages[site] = page_text(site)
        text_norm = " " + norm(e["beschreibung"] + " " + pages.get(site, "")) + " "
        scored = sorted(((cast_hits(cast.get(m["id"], []), text_norm), m) for m in e["_cands"]),
                        key=lambda x: len(x[0]), reverse=True)
        best_hits, best = scored[0]
        if len(e["_cands"]) == 1:
            ok = len(best_hits) >= 2
        else:
            ok = len(best_hits) >= 1 and len(best_hits) > len(scored[1][0])
        if ok:
            out[id(e)] = (dict(best), best_hits)
    return out


def display_title(e: dict, m: dict) -> str:
    """Deutscher Mediathek-Titel, bereinigt (ohne '- Spielfilm, USA 1972')."""
    via = m.get("_via") or e["variants"][0]
    t = clean_title(via) or via
    return t


# --------------------------------------------------------------------------
# Download + Umcodieren
# --------------------------------------------------------------------------
def find_tool(name: str) -> Optional[str]:
    for p in (shutil.which(name), "/opt/homebrew/bin/" + name, "/usr/local/bin/" + name):
        if p and os.path.exists(p):
            return p
    return None


def media_minutes(path: str) -> Optional[float]:
    """Laufzeit einer Videodatei in Minuten (über ffprobe), None wenn unbekannt."""
    probe = find_tool("ffprobe")
    if not probe or not os.path.exists(path):
        return None
    try:
        out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True, timeout=120).stdout.strip()
        return float(out) / 60.0
    except Exception:
        return None


def long_enough(path: str, expected_min: float, what: str) -> bool:
    """Schützt vor abgebrochenen Downloads: Datei muss fast so lang sein wie der Film."""
    got = media_minutes(path)
    if got is None:
        ok = os.path.exists(path) and os.path.getsize(path) > 50 * 1024 * 1024
        if not ok:
            log.warning("%s: Datei fehlt oder ist zu klein.", what)
        return ok
    need = max(1.0, expected_min * 0.9 - 3)
    if got < need:
        log.warning("%s unvollständig: %.1f min statt ca. %.0f min.", what, got, expected_min)
        return False
    return True


def _attrs(line: str) -> Dict[str, str]:
    return {k: v.strip('"') for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line)}


def hls_pick(url: str) -> Tuple[str, Optional[str]]:
    """Liest eine HLS-Master-Playlist und wählt die beste Videospur (höchste Auflösung) und die
    passende Tonspur (Standard bzw. Deutsch). Gibt (video_url, audio_url|None) zurück."""
    from urllib.parse import urljoin
    try:
        text = subprocess.run(["curl", "-sS", "-L", "--fail", "--retry", "3", url],
                              capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return url, None
    try:
        with open(os.path.join(LOG_DIR, "last_playlist.m3u8"), "w", encoding="utf-8") as f:
            f.write("# " + url + "\n" + text)
    except Exception:
        pass
    if "#EXT-X-STREAM-INF" not in text:
        return url, None
    lines = text.splitlines()
    audio: Dict[str, List[Dict[str, str]]] = {}
    variants = []
    for k, line in enumerate(lines):
        if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line:
            a = _attrs(line.split(":", 1)[1])
            audio.setdefault(a.get("GROUP-ID", ""), []).append(a)
        elif line.startswith("#EXT-X-STREAM-INF:"):
            a = _attrs(line.split(":", 1)[1])
            nxt = next((l for l in lines[k + 1:] if l and not l.startswith("#")), None)
            if nxt:
                h = 0
                m = re.match(r"(\d+)x(\d+)", a.get("RESOLUTION", ""))
                if m:
                    h = int(m.group(2))
                variants.append((h, int(a.get("BANDWIDTH", "0") or 0), urljoin(url, nxt), a.get("AUDIO")))
    if not variants:
        return url, None
    h, bw, vurl, group = max(variants, key=lambda v: (v[0], v[1]))
    aurl = None
    cands = [a for a in audio.get(group or "", []) if a.get("URI")]
    if cands:
        def score(a):
            lang = (a.get("LANGUAGE", "") + " " + a.get("NAME", "")).lower()
            ad = bool(re.search(r"audiodeskription|hörfassung|hoerfassung|\bad\b|descri", lang)
                      or "public.accessibility" in a.get("CHARACTERISTICS", ""))
            return (0 if ad else 1,
                    1 if re.search(r"\b(de|deu|ger)\b|deutsch", lang) else 0,
                    1 if a.get("DEFAULT") == "YES" else 0)
        best = max(cands, key=score)
        if score(best)[1] == 0:
            log.warning("HLS: keine deutsche Tonspur gefunden, nehme „%s“", best.get("NAME", "?"))
        aurl = urljoin(url, best["URI"])
        log.info("HLS: Video %sp (%d kbit/s), Ton „%s“", h, bw // 1000, best.get("NAME", "?"))
    else:
        log.info("HLS: Video %sp (%d kbit/s), Ton im Videostream", h, bw // 1000)
    return vurl, aurl


RECONNECT = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_on_network_error", "1",
             "-reconnect_delay_max", "30", "-rw_timeout", "60000000"]


def download_once(url: str, dest: str) -> bool:
    for p in (dest, dest + ".part"):
        if os.path.exists(p):
            os.remove(p)
    if ".m3u8" not in url.split("?")[0]:
        return curl_download(url, dest)
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        log.warning("HLS-Stream (m3u8) braucht ffmpeg (brew install ffmpeg) – übersprungen.")
        return False
    vurl, aurl = hls_pick(url)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + RECONNECT + ["-i", vurl]
    if aurl:
        cmd += RECONNECT + ["-i", aurl, "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    cmd += ["-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", dest]
    with open(os.path.join(LOG_DIR, "ffmpeg-last.log"), "w") as fl:
        rc = run(cmd, stdout=fl, stderr=subprocess.STDOUT)
    if rc != 0:
        log.warning("ffmpeg rc=%s, siehe logs/ffmpeg-last.log", rc)
    return rc == 0 and os.path.exists(dest)


def download_video(url: str, dest: str, expected_min: float = 0, tries: int = 3) -> bool:
    """Lädt herunter und prüft die Länge; bei abgebrochenem Download bis zu 3 Versuche."""
    for n in range(1, tries + 1):
        if download_once(url, dest) and (not expected_min or long_enough(dest, expected_min, "Download")):
            return True
        if n < tries:
            log.info("Download-Versuch %d fehlgeschlagen, neuer Versuch in 60 s …", n)
            time.sleep(60)
    return False


def german_audio_track(path: str) -> Optional[int]:
    """Nummer (ab 1) der deutschen Tonspur ohne Hörfassung; None wenn nicht ermittelbar."""
    probe = find_tool("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.run([probe, "-v", "error", "-select_streams", "a", "-show_entries",
                              "stream=index:stream_tags=language,title,handler_name:stream_disposition=default,visual_impaired",
                              "-of", "json", path], capture_output=True, text=True, timeout=120).stdout
        streams = json.loads(out).get("streams", [])
    except Exception:
        return None
    if not streams:
        return None
    best, best_score = 1, None
    for n, st in enumerate(streams, 1):
        tags = {k.lower(): str(v).lower() for k, v in (st.get("tags") or {}).items()}
        disp = st.get("disposition") or {}
        title = tags.get("title", "") + " " + tags.get("handler_name", "")
        ad = bool(disp.get("visual_impaired") or re.search(r"audiodeskription|hörfassung|\bad\b|descri", title))
        german = tags.get("language", "") in ("deu", "ger", "de") or "deutsch" in title
        sc = (0 if ad else 1, 1 if german else 0, 1 if disp.get("default") else 0, -n)
        if best_score is None or sc > best_score:
            best, best_score = n, sc
    if len(streams) > 1:
        log.info("Tonspur %d von %d gewählt (Deutsch, ohne Hörfassung).", best, len(streams))
    return best


def encode(cfg: dict, src: str, dest: str) -> bool:
    cmd = [cfg["handbrake_cli"], "-i", src, "-o", dest, "--preset", cfg["handbrake_preset"]]
    track = german_audio_track(src)
    if track:
        # Spur zweimal angeben: das Preset macht daraus AAC-Stereo + Surround-Spur
        cmd += ["--audio", "%d,%d" % (track, track)]
    with open(os.path.join(LOG_DIR, "handbrake-last.log"), "w") as hb:
        rc = run(cmd, stdout=hb, stderr=subprocess.STDOUT)
    if rc != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 10 * 1024 * 1024:
        log.warning("HandBrake fehlgeschlagen (rc=%s), siehe logs/handbrake-last.log", rc)
        return False
    return True


def process(cfg: dict, item: dict, done: dict) -> bool:
    e, m = item["entry"], item["imdb"]
    name = "%s (%s)" % (safe_name(item["title"]), m["year"])
    folder = os.path.join(cfg["target_dir"], name)
    final = os.path.join(folder, name + cfg["file_extension"])
    if os.path.exists(final):
        log.info("Existiert schon: %s", final)
        done[m["id"]] = {"name": name, "path": final, "rating": m.get("rating"),
                         "sender": e["sender"], "added": dt.date.today().isoformat()}
        return True

    size_mb = 0.0
    try:
        size_mb = float(e["groesse"] or 0)
    except ValueError:
        pass
    need = cfg["min_free_gb"] * 1024 ** 3 + max(size_mb, 3000) * 2.2 * 1024 ** 2
    if shutil.disk_usage(cfg["target_dir"]).free < need:
        log.warning("Zu wenig Platz auf der SSD – Lauf wird beendet.")
        raise MemoryError("disk")

    url = e["url_hd"] or e["url"]
    src = os.path.join(TMP_DIR, m["id"] + ".source.mp4")
    out = os.path.join(TMP_DIR, m["id"] + ".encoded" + cfg["file_extension"])
    log.info("▶ %s – IMDb %.1f (%s Stimmen) – %s/%s", name, m.get("rating", 0),
             m.get("votes", 0), e["sender"], e["thema"])
    t0 = time.time()
    try:
        if not download_video(url, src, e["minutes"]):
            if e["url_hd"] and e["url"] and url != e["url"]:
                log.info("Versuche Standard-Qualität …")
                if not download_video(e["url"], src, e["minutes"]):
                    return False
            else:
                return False
        if not encode(cfg, src, out):
            return False
        if not long_enough(out, e["minutes"], "Umcodierte Datei"):
            return False
        os.makedirs(folder, exist_ok=True)
        shutil.move(out, final)
    finally:
        for p in (src, src + ".part", out):
            if os.path.exists(p):
                os.remove(p)
    log.info("✔ fertig in %.0f min: %s", (time.time() - t0) / 60, final)
    done[m["id"]] = {
        "name": name, "path": final, "rating": m.get("rating"), "votes": m.get("votes"),
        "sender": e["sender"], "mediathek_titel": e["titel"], "website": e["website"],
        "added": dt.date.today().isoformat(),
    }
    return True


# --------------------------------------------------------------------------
# Hauptablauf
# --------------------------------------------------------------------------
def setup_logging(dry: bool) -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join(LOG_DIR, "%s%s.log" % (stamp, "_dryrun" if dry else ""))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    log.setLevel(logging.DEBUG)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(sh)
    return stamp


def prune_logs(days: int) -> None:
    if not days:
        return
    limit = time.time() - days * 86400
    for name in os.listdir(LOG_DIR):
        p = os.path.join(LOG_DIR, name)
        if (name.endswith(".log") or name.endswith(".md")) and os.path.isfile(p) \
                and os.path.getmtime(p) < limit and not name.endswith("-last.log"):
            try:
                os.remove(p)
            except OSError:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="nur suchen, nichts laden")
    ap.add_argument("--limit", type=int, default=None, help="max. Filme in diesem Lauf")
    ap.add_argument("--test-imessage", action="store_true",
                    help="nur eine Test-iMessage senden (erteilt die macOS-Berechtigung)")
    ap.add_argument("--config-erstellen", action="store_true",
                    help="config.json im beschrifteten Format mit den aktuellen Werten (neu) schreiben")
    args = ap.parse_args()

    cfg = load_config()
    if args.config_erstellen:
        path = os.path.join(BASE_DIR, "config.json")
        save_json(path, config_document(cfg))
        print("config.json geschrieben: %s" % path)
        return 0
    for d in (STATE_DIR, LOG_DIR, CACHE_DIR, TMP_DIR):
        os.makedirs(d, exist_ok=True)
    stamp = setup_logging(args.dry_run)
    prune_logs(int(cfg.get("log_keep_days") or 0))

    if args.test_imessage:
        ok = send_imessage(cfg, "🎬 Test von der Mediathek-Automatik – iMessage funktioniert.")
        return 0 if ok else 1

    try:
        return run_main(cfg, args, stamp)
    except Exception as ex:  # noqa
        log.exception("Lauf abgebrochen: %s", ex)
        if not args.dry_run:
            send_imessage(cfg, "❌ Mediathek-Lauf abgebrochen: %s\n(Details im Log auf der SSD)" % ex)
        return 1


def run_main(cfg: dict, args, stamp: str) -> int:
    if not os.path.isdir(cfg["target_dir"]):
        log.error("Zielordner nicht da (SSD nicht angeschlossen?): %s", cfg["target_dir"])
        if not args.dry_run:
            send_imessage(cfg, "⚠️ Mediathek-Lauf übersprungen: SSD nicht angeschlossen.")
        return 2
    if not args.dry_run and not os.path.exists(cfg["handbrake_cli"]):
        raise RuntimeError("HandBrakeCLI nicht gefunden: %s" % cfg["handbrake_cli"])

    lock = open(os.path.join(STATE_DIR, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("Es läuft bereits ein anderer Durchgang.")
        return 3

    done_path = os.path.join(STATE_DIR, "done.json")
    fail_path = os.path.join(STATE_DIR, "failed.json")
    done = load_json(done_path, {})
    failed = load_json(fail_path, {})
    ensure_list(cfg, done)
    list_ids, list_names, list_entries = read_list(list_path(cfg))

    cands = select_candidates(cfg, fetch_filmlist(cfg))
    wanted = {norm(v) for e in cands for v in e["variants"]} | list_wanted(list_entries)
    by_title, info = build_imdb_index(cfg, fetch_imdb(cfg), wanted)
    # Filme aus der Liste über IMDb erkennen (z. B. "Apocalypse Now (1979)" = "… Final Cut")
    list_ids |= set(resolve_list_ids(list_entries, by_title, info))
    # Zusätzliche, von Hand zugeordnete IMDb-IDs (Titel, die IMDb anders schreibt)
    list_ids |= set(load_json(os.path.join(STATE_DIR, "extra_ids.json"), {}).keys())
    log.info("Liste: %d Einträge, %d davon IMDb zugeordnet.", len(list_entries), len(list_ids))

    picks: Dict[str, dict] = {}
    reasons: Dict[str, int] = {}
    ambiguous: List[str] = []
    results = []
    open_cases = []   # mehrdeutig/unsicher, aber mind. ein Kandidat erfüllt die Kriterien
    for e in cands:
        m, why = match_entry(cfg, e, by_title, info)
        if not m and e.get("_cands"):
            e["_cands"] = [x for x in e["_cands"] if qualifies(cfg, x)]
            if e["_cands"]:
                open_cases.append(e)
        results.append((e, m, why))
    open_ids = {id(e) for e in open_cases}
    resolved: Dict[int, Tuple[dict, List[str]]] = {}
    if open_cases and cfg.get("cast_check", True):
        log.info("Besetzungs-Abgleich für %d unklare Filme …", len(open_cases))
        resolved = resolve_by_cast(cfg, open_cases)
        log.info("Besetzungs-Abgleich: %d davon geklärt.", len(resolved))
    cast_notes: Dict[str, str] = {}
    for e, m, why in results:
        if not m and id(e) in resolved:
            m, found = resolved[id(e)]
            why = "ok (Besetzung)"
            cast_notes[m["id"]] = ", ".join(found[:3])
            log.info("✓ Über Besetzung geklärt: %s → %s (%s) – %s",
                     e["titel"], m["title"], m["year"], cast_notes[m["id"]])
        if not m:
            key = why.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
            if id(e) in open_ids:
                ambiguous.append("%s [%s] → %s" % (e["titel"], e["sender"], why))
            continue
        if m.get("rating", 0) < cfg["min_rating"] or m.get("votes", 0) <= cfg["min_votes"]:
            continue
        if cfg.get("min_year") and (m.get("year") or 0) < cfg["min_year"]:
            continue
        subt = "untertitel" in e["titel"].casefold()
        score = (0 if subt else 1, 1 if e["url_hd"] else 0, e["minutes"])
        old = picks.get(m["id"])
        if not old or score > old["score"]:
            picks[m["id"]] = {"entry": e, "imdb": m, "score": score, "title": display_title(e, m)}
    log.info("Gründe für Nicht-Treffer: %s", reasons)

    def already(tid: str, p: dict) -> bool:
        if tid in done or tid in list_ids:
            return True
        t = safe_name(p["title"])
        return norm("%s (%s)" % (t, p["imdb"]["year"])) in list_names or norm(t) in list_names

    todo = [p for tid, p in picks.items()
            if not already(tid, p) and failed.get(tid, {}).get("count", 0) < 3]
    todo.sort(key=lambda p: (p["imdb"].get("rating", 0), p["imdb"].get("votes", 0)), reverse=True)
    limit = args.limit if args.limit is not None else cfg["max_per_run"]
    log.info("%d Filme ab IMDb %.1f gefunden, davon %d neu; bearbeite bis zu %d.",
             len(picks), cfg["min_rating"], len(todo), limit)

    report = ["# Mediathek-Lauf %s%s" % (stamp, " (Testlauf)" if args.dry_run else ""), ""]
    report.append("## Neue Filme (IMDb ab %.1f, mehr als %d Stimmen, ab %s)" % (
        cfg["min_rating"], cfg["min_votes"], cfg.get("min_year") or "-"))
    for p in todo:
        m, e = p["imdb"], p["entry"]
        report.append("- %s (%s) – IMDb %.1f, %d Stimmen – %s / %s – „%s“ – %s" % (
            p["title"], m["year"], m.get("rating", 0), m.get("votes", 0), e["sender"],
            e["thema"], e["titel"], "HD" if e["url_hd"] else "SD"))
    if cast_notes:
        report += ["", "## Über die Besetzung zugeordnet"]
        for tid, note in cast_notes.items():
            if tid in picks:
                p = picks[tid]
                report.append("- %s (%s) – gefunden: %s" % (p["title"], p["imdb"]["year"], note))
    if ambiguous:
        report += ["", "## Nicht eindeutig zuzuordnen, übersprungen",
                   "(nur Titel, bei denen mindestens ein IMDb-Kandidat die Kriterien erfüllen würde)"]
        report += ["- " + a for a in ambiguous[:100]]

    added: List[str] = []
    failed_now: List[str] = []
    disk_full = False
    if not args.dry_run:
        for p in todo[:limit]:
            tid = p["imdb"]["id"]
            try:
                ok = process(cfg, p, done)
            except MemoryError:
                disk_full = True
                break
            except Exception as ex:  # noqa
                log.exception("Fehler bei %s: %s", p["title"], ex)
                ok = False
            if ok:
                rec = done[tid]
                added.append("%s – IMDb %.1f" % (rec["name"], rec.get("rating") or 0))
                append_list(cfg, rec, tid)
                failed.pop(tid, None)
            else:
                f = failed.setdefault(tid, {"count": 0, "title": p["title"]})
                f["count"] += 1
                f["last"] = dt.date.today().isoformat()
                failed_now.append("%s (%s)" % (p["title"], p["imdb"]["year"]))
            save_json(done_path, done)
            save_json(fail_path, failed)
        report += ["", "## In diesem Lauf hinzugefügt"] + ["- " + a for a in added]
        if failed_now:
            report += ["", "## Fehlgeschlagen"] + ["- " + a for a in failed_now]

    with open(os.path.join(LOG_DIR, "report_%s%s.md" % (stamp, "_dryrun" if args.dry_run else "")),
              "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    if args.dry_run:
        msg = "Testlauf: %d neue Filme gefunden" % len(todo)
    else:
        msg = "%d Filme hinzugefügt" % len(added)
        lines = ["🎬 Mediathek-Lauf vom %s" % dt.date.today().strftime("%d.%m.%Y")]
        if added:
            lines.append("✅ %d %s heruntergeladen und umgewandelt:" %
                         (len(added), "Film" if len(added) == 1 else "Filme"))
            lines += ["• " + a for a in added]
        else:
            lines.append("Keine neuen Filme.")
        if failed_now:
            lines.append("⚠️ Fehlgeschlagen: " + ", ".join(failed_now))
        if disk_full:
            lines.append("⚠️ Abgebrochen: zu wenig Platz auf der SSD.")
        rest = max(0, len(todo) - len(added) - len(failed_now))
        if rest:
            lines.append("Noch %d weitere Filme in der Warteschlange." % rest)
        try:
            free = shutil.disk_usage(cfg["target_dir"]).free / 1e9
            lines.append("Frei auf der SSD: %.0f GB" % free)
        except Exception:
            pass
        if added or failed_now or disk_full or cfg.get("imessage_when_nothing_new", True):
            send_imessage(cfg, "\n".join(lines))
    log.info(msg)
    if cfg.get("notify"):
        notify("Mediathek-Filme", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
