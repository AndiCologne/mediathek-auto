#!/bin/bash
# Richtet den wöchentlichen Lauf ein: jeden Mittwoch um 02:00 Uhr.
# Aufruf im Terminal:
#   bash "/Volumes/TB4SSD/AILocalSandbox/Movies/.mediathek-auto/install.sh"
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="local.mediathek-auto"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Python wählen (Homebrew bevorzugt, sonst macOS)
PY=""
for p in /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
    PY="$p"; break
  fi
done
[ -z "$PY" ] && { echo "❌ Kein Python 3.9+ gefunden. Bitte: brew install python"; exit 1; }
echo "✔ Python: $PY ($("$PY" --version))"

[ -x /opt/homebrew/bin/HandBrakeCLI ] && echo "✔ HandBrakeCLI gefunden" || echo "⚠️  /opt/homebrew/bin/HandBrakeCLI fehlt"
if [ -x /opt/homebrew/bin/ffmpeg ] || command -v ffmpeg >/dev/null; then
  echo "✔ ffmpeg gefunden"
else
  echo "ℹ️  ffmpeg fehlt – einzelne Filme, die nur als Stream (m3u8) vorliegen, werden übersprungen."
  echo "   Optional nachinstallieren: brew install ffmpeg"
fi

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>$PY</string>
    <string>$DIR/mediathek_auto.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>3</integer>
    <key>Hour</key><integer>2</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LANG</key><string>de_DE.UTF-8</string>
  </dict>
  <key>StandardOutPath</key><string>$DIR/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err.log</string>
  <key>LowPriorityIO</key><true/>
  <key>Nice</key><integer>5</integer>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✔ Zeitplan aktiv: jeden Mittwoch 02:00 Uhr ($PLIST)"

# Test-iMessage über denselben Hintergrund-Mechanismus wie der nächtliche Lauf,
# damit macOS jetzt (und nicht nachts um 2) nach der Berechtigung für „Nachrichten“ fragt.
if grep -q '"imessage_to" *: *"[^"]' "$DIR/config.json" 2>/dev/null; then
  TLABEL="local.mediathek-auto.imessagetest"
  TPLIST="$HOME/Library/LaunchAgents/$TLABEL.plist"
  cat > "$TPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$TLABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$PY</string><string>$DIR/mediathek_auto.py</string><string>--test-imessage</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$TLABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$TPLIST"
  echo "📱 Test-iMessage wird gesendet – falls macOS fragt, ob Python „Nachrichten“ steuern darf: Erlauben."
  sleep 30
  launchctl bootout "gui/$(id -u)/$TLABEL" 2>/dev/null || true
  rm -f "$TPLIST"
else
  echo "ℹ️  Keine iMessage-Adresse in config.json – Abschlussberichte per iMessage sind aus."
fi
echo
echo "Nächste Schritte:"
echo "  1) Testlauf ohne Download:"
echo "     \"$PY\" \"$DIR/mediathek_auto.py\" --dry-run"
echo "  2) Einen echten Film als Probe:"
echo "     \"$PY\" \"$DIR/mediathek_auto.py\" --limit 1"
echo "  3) Hintergrund-Lauf sofort auslösen (prüft die Rechte für die SSD):"
echo "     launchctl kickstart gui/$(id -u)/$LABEL"
