#!/usr/bin/env bash
# frn_adn aktualisieren: neuen Stand holen, Python-Pakete, Dashboard neu starten.
# Der FRN-Server läuft dabei weiter. Daten (SQLite), Benutzer und Einstellungen bleiben erhalten.
# Den Java-FRN-Server selbst aktualisiert das Admin-Portal (Settings → Check for update)
# oder ein erneuter Aufruf von scripts/install.sh.
#   cd /opt/adn-frn-server && sudo ./scripts/update.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten."; exit 1; }
cd "$DIR"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -q --no-install-recommends certbot
fi
if [ -d .git ]; then
    git config --global --add safe.directory "$DIR" 2>/dev/null || true
    git pull --ff-only
else
    echo "Kein git-Verzeichnis: neuen Stand nach $DIR kopieren und dieses Skript erneut starten."
fi
"$DIR/venv/bin/pip" install -q -r requirements.txt
command -v frnadn >/dev/null && frnadn write-config >/dev/null || true
systemctl restart frnadn
echo "✓ frn_adn $(sed -n 's/__version__ = "\(.*\)"/\1/p' frnadn/__init__.py) läuft. Geänderte server.properties nutzt der FRN-Server nach einem Neustart (Admin-Portal)."
