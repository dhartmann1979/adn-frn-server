#!/usr/bin/env bash
# ADN-FRN-Server aktualisieren – dasselbe Verfahren wie „Update jetzt“ im Adminbereich (scripts/n8-admin.sh update):
# nur vorspulen auf origin, Python-Pakete, Konfiguration des FRN-Servers, Berechtigungen und sudo prüfen/korrigieren,
# beide Dienste neu starten, Weboberfläche prüfen – antwortet sie nicht, zurück auf den alten Stand.
#   sudo /opt/adn-frn-server/scripts/update.sh
# Den Java-FRN-Server aktualisiert der Adminbereich (System → Updates) oder ein erneuter Aufruf von scripts/install.sh.
set -euo pipefail
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten."; exit 1; }
if ! command -v certbot >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends certbot >/dev/null || true
fi
chmod 755 "$HERE/n8-admin.sh"
exec "$HERE/n8-admin.sh" update "$@"
