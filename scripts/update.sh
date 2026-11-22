#!/usr/bin/env bash
# frn_adn aktualisieren: neuen Stand holen, Python-Pakete, Dateirechte und beide Dienste neu starten.
# Der FRN-Server startet mit, damit sein Live-Status im Dashboard frisch eingelesen wird.
# Den Java-FRN-Server selbst aktualisiert das Admin-Portal (System → Software-Updates)
# oder ein erneuter Aufruf von scripts/install.sh.
#   cd /opt/adn-frn-server && sudo ./scripts/update.sh
#
# Das Skript stellt außerdem die Dateirechte so ein, dass das Dashboard sich danach auch
# selbst aus dem Admin-Portal aktualisieren kann ("Upgrade Dashboard now").
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten."; exit 1; }
cd "$DIR"

# Dienstbenutzer aus der installierten Unit lesen (Vorgabe: frnadn)
SVC_USER="$(systemctl show -p User --value frnadn.service 2>/dev/null || true)"
[ -n "$SVC_USER" ] || SVC_USER=frnadn

if ! command -v certbot >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
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
if id "$SVC_USER" >/dev/null 2>&1; then
    # Ohne diese Rechte kann das Dashboard seinen eigenen git-Stand weder lesen noch aktualisieren
    chown -R "$SVC_USER:$SVC_USER" "$DIR"
fi
command -v frnadn >/dev/null && frnadn write-config >/dev/null || true
systemctl restart frn-server
systemctl restart frnadn
echo "✓ frn_adn $(sed -n 's/__version__ = "\(.*\)"/\1/p' frnadn/__init__.py) und FRN-Server neu gestartet. Daten (SQLite), Benutzer und Einstellungen bleiben erhalten."
