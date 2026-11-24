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
# N8 update guard (ab 2.6.0): Rollback, wenn das Dashboard nach einem Update nicht hochkommt.
# Fehlt die Zeile in der installierten Unit, wird sie ergänzt (Pfade aus der Unit selbst).
UNIT=/etc/systemd/system/frnadn.service
chmod 0755 "$DIR/scripts/"*.sh 2>/dev/null || true
if [ -f "$UNIT" ] && ! grep -q "n8-update-guard" "$UNIT"; then
    WD="$(sed -n 's/^WorkingDirectory=//p' "$UNIT" | head -n 1)"; WD="${WD:-$DIR}"
    DD="$(sed -n 's/^Environment=FRNADN_DATA=//p' "$UNIT" | head -n 1)"; DD="${DD:-/var/lib/frnadn}"
    sed -i "s#^ExecStart=#ExecStartPre=-/bin/sh ${WD}/scripts/n8-update-guard.sh ${WD} ${DD}\nExecStart=#" "$UNIT"
    systemctl daemon-reload
    echo "✓ Update-Prüfung mit Rollback in frnadn.service eingetragen"
fi
systemctl restart frn-server
systemctl restart frnadn
echo "✓ frn_adn $(sed -n 's/__version__ = "\(.*\)"/\1/p' frnadn/__init__.py) und FRN-Server neu gestartet. Daten (SQLite), Benutzer und Einstellungen bleiben erhalten."
