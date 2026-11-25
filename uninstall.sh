#!/bin/bash
# Entfernt den wöchentlichen Zeitplan (Skript, Logs und Filme bleiben erhalten).
LABEL="local.mediathek-auto"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "✔ Zeitplan entfernt."
