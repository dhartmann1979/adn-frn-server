#!/usr/bin/env bash
# =============================================================================
#  frn_adn – geführte Installation auf Debian / Ubuntu / Raspberry Pi OS
#
#  Installiert Schritt für Schritt:
#    • den Java-FRN-Server von freeradionetwork.de (FRN_Server.jar)
#    • frn_adn: Dashboard und Admin-Portal (Design: Auf der NachtSchicht)
#  Alle Einstellungen liegen in SQLite; frn_adn schreibt daraus nur die
#  Dateien, die der FRN-Server braucht (server.properties, log4j.xml, acl/).
#
#    sudo ./scripts/install.sh
#
#  Ein zweiter Aufruf aktualisiert die Installation; vorhandene Werte sind
#  dann die Vorgaben, Daten und Benutzer bleiben erhalten.
#
#  Umgebungsvariablen (optional):
#    FRNADN_DIR=/opt/frnadn       Programmverzeichnis des Dashboards
#    FRNADN_PORT=80               Web-Port des Dashboards
#    FRN_DIR=/opt/frn-server      Verzeichnis für FRN_Server.jar
#    FRN_ZIP=/pfad/FRN_Server.zip vorhandenes Paket statt Download
#    FRNADN_YES=1                 keine Fragen, Vorgaben übernehmen
# =============================================================================
set -euo pipefail

DIR="${FRNADN_DIR:-/opt/frnadn}"
PORT="${FRNADN_PORT:-80}"
FRN_DIR="${FRN_DIR:-/opt/frn-server}"
DATA=/var/lib/frnadn
FRN_HOME="$DATA/frn"
SVC_USER=frnadn
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG=/var/log/frnadn-install.log
YES="${FRNADN_YES:-0}"
DL_URL="https://freeradionetwork.de/assets/files/FRN_Server.zip"
STEPS=8

C='\033[0;36m'; G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1m'; D='\033[2m'; N='\033[0m'
step()  { echo; echo -e "${C}━━ Schritt $1/${STEPS}: $2${N}"; }
ok()    { echo -e "   ${G}✓${N} $*"; }
warn()  { echo -e "   ${Y}!${N} $*"; }
fail()  { echo -e "   ${R}✗ $*${N}"; exit 1; }
info()  { echo -e "   ${D}$*${N}"; }

# ask VAR "Frage" "Vorgabe"  – Enter übernimmt die Vorgabe
ask() {
    local __v="$1" q="$2" def="${3:-}" ans=""
    if [ "$YES" = 1 ] || [ ! -t 0 ]; then printf -v "$__v" '%s' "$def"; return 0; fi
    read -r -p "   $q [${def}]: " ans || true
    printf -v "$__v" '%s' "${ans:-$def}"
    return 0
}
ask_secret() {
    local __v="$1" q="$2" ans=""
    read -r -s -p "   $q: " ans || true; echo
    printf -v "$__v" '%s' "$ans"
    return 0
}
yesno() {   # yesno "Frage" j|n
    local __yn=""
    ask __yn "$1 (j/n)" "$2"
    [[ "$__yn" =~ ^[jJyY] ]]
}
interactive() { [ "$YES" != 1 ] && [ -t 0 ]; }
ver_of() { sed -n '1s/^\xEF\xBB\xBF//; 1s/.*Release V *\([0-9.]*\) *(Build *\([0-9.]*\)).*/\1 (\2)/p'; }

[ "$(id -u)" -eq 0 ] || fail "Bitte mit sudo starten: sudo $0"
exec > >(tee -a "$LOG") 2>&1

echo -e "
   ${B}🌙 Auf der NachtSchicht – FRN-Server mit Dashboard${N}
   Java-FRN-Server von freeradionetwork.de · Dashboard · Admin-Portal · Einstellungen in SQLite
   Fragen haben eine Vorgabe in [Klammern] – Enter übernimmt sie.
"

# ---------------------------------------------------------------------------
step 1 "System prüfen"
. /etc/os-release 2>/dev/null || true
ok "${PRETTY_NAME:-Linux} · $(dpkg --print-architecture 2>/dev/null || uname -m)"
command -v systemctl >/dev/null || fail "systemd wird gebraucht."
command -v apt-get >/dev/null || fail "Dieses Skript ist für Debian, Ubuntu und Raspberry Pi OS (apt)."

# ---------------------------------------------------------------------------
step 2 "Pakete: Python und Java"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -q --no-install-recommends python3 python3-venv python3-pip sudo curl unzip ca-certificates >/dev/null
if ! command -v java >/dev/null; then
    info "Java wird installiert (der FRN-Server ist ein Java-Programm) …"
    apt-get install -y -q --no-install-recommends default-jre-headless >/dev/null || fail "Java (default-jre-headless) ließ sich nicht installieren."
fi
JAVA="$(command -v java)"
ok "Python $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])') · $("$JAVA" -version 2>&1 | grep -v '^Picked up' | head -1)"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || fail "Python 3.9 oder neuer wird gebraucht."

# ---------------------------------------------------------------------------
step 3 "FRN-Server von freeradionetwork.de"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin "$SVC_USER"
mkdir -p "$FRN_DIR"
INSTALLED="$( { ver_of < "$FRN_DIR/releasenotes.txt"; } 2>/dev/null || true)"
GET=1
if [ -f "$FRN_DIR/FRN_Server.jar" ]; then
    ok "vorhanden: Java FRN_Server ${INSTALLED:-?}"
    LATEST="$(curl -fsSL --max-time 20 https://freeradionetwork.de/assets/files/FRN_Server_releasenotes.txt 2>/dev/null | head -c 300 | tr -d '\r' | ver_of || true)"
    GET=0
    if [ -n "$LATEST" ] && [ "$LATEST" != "$INSTALLED" ]; then
        yesno "Neue Version ${LATEST} auf freeradionetwork.de – jetzt aktualisieren?" j && GET=1
    fi
fi
if [ "$GET" = 1 ]; then
    TMP="$(mktemp -d)"
    if [ -n "${FRN_ZIP:-}" ]; then
        cp "$FRN_ZIP" "$TMP/frn.zip"
    else
        info "Lade ${DL_URL} …"
        curl -fsSL --max-time 300 -o "$TMP/frn.zip" "$DL_URL" || fail "Download fehlgeschlagen. Paket von https://freeradionetwork.de/frn_server.html laden und mit FRN_ZIP=/pfad/FRN_Server.zip erneut starten."
    fi
    unzip -q -o "$TMP/frn.zip" -d "$TMP/x" || fail "Das Paket ist kein gültiges ZIP."
    JAR="$(find "$TMP/x" -name FRN_Server.jar | head -1)"
    [ -n "$JAR" ] || fail "Im Paket fehlt FRN_Server.jar."
    PKG="$(dirname "$JAR")"
    install -m 0644 "$JAR" "$FRN_DIR/FRN_Server.jar"
    for f in releasenotes.txt properties_doc.pdf server_example.properties; do
        [ -f "$PKG/$f" ] && install -m 0644 "$PKG/$f" "$FRN_DIR/$f"
    done
    rm -rf "$TMP"
    ok "installiert: Java FRN_Server $(ver_of < "$FRN_DIR/releasenotes.txt") nach ${FRN_DIR}"
fi
chown -R "$SVC_USER:$SVC_USER" "$FRN_DIR"           # frn_adn installiert Updates aus dem Admin-Portal

# ---------------------------------------------------------------------------
step 4 "Dashboard frn_adn nach ${DIR}"
mkdir -p "$DIR" "$DATA" "$FRN_HOME/acl" "$FRN_HOME/logs"
if [ "$SRC_DIR" != "$DIR" ]; then
    rm -rf "$DIR/frnadn" "$DIR/static"
    cp -a "$SRC_DIR/frnadn" "$SRC_DIR/static" "$SRC_DIR/scripts" "$SRC_DIR/systemd" "$SRC_DIR/requirements.txt" "$DIR/"
    if [ -d "$SRC_DIR/.git" ]; then rm -rf "$DIR/.git"; cp -a "$SRC_DIR/.git" "$DIR/"; fi
fi
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --upgrade pip >/dev/null
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt" >/dev/null
ok "Python-Umgebung mit FastAPI und uvicorn"
for g in systemd-journal adm; do getent group "$g" >/dev/null && usermod -aG "$g" "$SVC_USER"; done
chown -R "$SVC_USER:$SVC_USER" "$DATA"
chmod 750 "$DATA" "$FRN_HOME"
ok "Benutzer ${SVC_USER} · Daten in ${DATA} (SQLite) · Konfiguration des FRN-Servers in ${FRN_HOME}"

SC="$(command -v systemctl)"
cat > /etc/sudoers.d/frnadn <<EOF
# frn_adn: the dashboard controls the FRN server; only the superadmin may reboot or shut down
$SVC_USER ALL=(root) NOPASSWD: $SC start frn-server.service, $SC stop frn-server.service, $SC restart frn-server.service, \\
    $SC reboot, $SC poweroff
EOF
chmod 440 /etc/sudoers.d/frnadn
visudo -cq -f /etc/sudoers.d/frnadn || fail "sudoers-Regel fehlerhaft"

cat > /usr/local/bin/frnadn <<EOF
#!/bin/sh
# frn_adn command line: frnadn set-superadmin NAME | reset-password NAME | add-account EMAIL CALL | show-settings | write-config
cd "$DIR" && exec sudo -u $SVC_USER env FRNADN_DATA=$DATA FRNADN_FRN_HOME=$FRN_HOME FRNADN_FRN_JAR=$FRN_DIR/FRN_Server.jar "$DIR/venv/bin/python" -m frnadn "\$@"
EOF
chmod 755 /usr/local/bin/frnadn
ok "Befehl ${B}frnadn${N} (z. B. sudo frnadn reset-password NAME)"

PY="$DIR/venv/bin/python"
run_app() { (cd "$DIR" && sudo -u "$SVC_USER" env FRNADN_DATA="$DATA" FRNADN_FRN_HOME="$FRN_HOME" FRNADN_FRN_JAR="$FRN_DIR/FRN_Server.jar" "$PY" -m frnadn "$@"); }
CUR="$(run_app show-settings 2>/dev/null || echo '{}')"
cget() { python3 -c "import json,sys; d=json.loads(sys.argv[1] or '{}'); v=d.get(sys.argv[2], ''); print(', '.join(v) if isinstance(v, list) else v)" "$CUR" "$1" 2>/dev/null || true; }
cdef() { local v; v="$(cget "$1")"; echo "${v:-$2}"; }

# ---------------------------------------------------------------------------
step 5 "Superadmin für das Admin-Portal"
SA_USER=""; SA_PASS=""; SA_NEW=1
if [ "$(cget _superadmin)" = "True" ]; then
    ok "Ein Superadmin ist schon angelegt."
    SA_NEW=0
    if interactive && yesno "Superadmin neu setzen (anderer Name oder neues Passwort)?" n; then SA_NEW=1; fi
else
    info "Der Superadmin darf alles – auch Admins anlegen und die Maschine neu starten."
    info "Es gibt keinen Werks-Login: ohne Superadmin kann sich niemand anmelden."
fi
if [ "$SA_NEW" = 1 ]; then
    if ! interactive; then
        warn "Keine Eingabe möglich – Superadmin später anlegen: ${B}sudo frnadn set-superadmin NAME${N}"
    else
        while :; do
            ask SA_USER "Benutzername des Superadmins" "admin"
            [[ "$SA_USER" =~ ^[A-Za-z0-9._@-]{2,32}$ ]] && break
            warn "2–32 Zeichen: Buchstaben, Ziffern, . _ @ -"
        done
        while :; do
            ask_secret SA_PASS "Passwort für ${SA_USER} (min. 10 Zeichen)"
            if [ ${#SA_PASS} -lt 10 ]; then warn "zu kurz"; continue; fi
            ask_secret SA_REP "Passwort wiederholen"
            [ "$SA_PASS" = "$SA_REP" ] && break
            warn "Die Passwörter sind verschieden."
        done
        ok "wird als scrypt-Hash gespeichert – das Passwort selbst steht nirgends"
    fi
fi

# ---------------------------------------------------------------------------
step 6 "FRN-Server einrichten"
CONFIGURE=1
if [ -n "$(cget _rooms)" ] && interactive; then
    ok "Vorhanden: $(cget frn.address):$(cget frn.port) · Räume $(cget _rooms) · $( [ "$(cget frn.standalone)" = True ] && echo Stand-alone || echo "SystemManager $(cget sysman.host)")"
    yesno "Einstellungen jetzt ändern? (geht auch später im Admin-Portal)" n || CONFIGURE=0
fi
umask 077
if [ "$CONFIGURE" = 1 ]; then
    info "Betriebsart:"
    info "  1 = am SystemManager sysman.freeradionetwork.de anmelden – öffentlicher Server im FRN-System,"
    info "      die Logins prüft der SystemManager. Du brauchst dein FRN-Konto (E-Mail und Passwort)."
    info "  2 = Stand-alone – eigenständig, z. B. für einen eigenen Verbund oder das Heimnetz;"
    info "      die Logins prüft die eigene Passwortliste im Admin-Portal."
    MODE_DEF=1; [ "$(cget frn.standalone)" = True ] && MODE_DEF=2
    ask MODE "Betriebsart (1/2)" "$MODE_DEF"
    STANDALONE=false; LAN=false; SM_EMAIL="$(cget sysman.email)"; SM_PASS=""
    if [ "$MODE" = 2 ]; then
        STANDALONE=true
        if yesno "LAN-Adresse als Serveradresse erlauben (nur fürs Heimnetz)?" "$( [ "$(cget frn.allow_lan)" = True ] && echo j || echo n)"; then LAN=true; fi
    else
        ask SM_EMAIL "E-Mail deines FRN-Kontos (sysman_auth_emailaddr)" "$SM_EMAIL"
        if interactive; then ask_secret SM_PASS "Passwort dieses FRN-Kontos (Enter = unverändert)"; fi
        info "Der SystemManager prüft beim Start, ob der Server von außen erreichbar ist."
        info "Richte die Portweiterleitung im Router deshalb VOR dem Start ein (TCP, Port siehe unten)."
    fi
    ask HOST "Öffentlicher Hostname oder IP des Servers (server_addr)" "$(cget frn.address)"
    [ -n "$HOST" ] || warn "Ohne Serveradresse startet der FRN-Server nicht – später im Admin-Portal eintragen."
    ask FPORT "FRN-Port (TCP) für die Clients (server_port)" "$(cdef frn.port 10024)"
    ask OEMAIL "Server-Besitzer: E-Mail mit OWNER-Rechten (Enter = FRN-Konto)" "$(cdef frn.owner_email "$SM_EMAIL")"
    ask OCALL "Server-Besitzer: Rufzeichen (für das Dashboard)" "$(cget frn.owner_callsign)"
    ask ONAME "Server-Besitzer: Name" "$(cget frn.owner_name)"
    ROOMS_DEF="$(cget _rooms)"; [ -n "$ROOMS_DEF" ] || ROOMS_DEF="Test, Nachtschicht, World"
    info "Räume: Der erste wird net00 – beim Java-FRN-Server immer der Test-/Parrot-Raum (Echotest)."
    ask ROOMS "Räume (mit Komma getrennt)" "$ROOMS_DEF"
    TESTROOM="$(echo "$ROOMS" | cut -d, -f1 | xargs)"
    OTHERS="$(echo "$ROOMS" | cut -s -d, -f2- | xargs)"
    DEFROOM_DEF="$(cget frn.default_room)"; [ -n "$DEFROOM_DEF" ] || DEFROOM_DEF="$(echo "$OTHERS" | cut -d, -f1 | xargs)"
    ask DEFROOM "Standardraum (für Clients mit unbekanntem Raum)" "${DEFROOM_DEF:-$TESTROOM}"
    ask TITLE "Titel des Dashboards" "$(cdef dashboard.title 'Auf der NachtSchicht')"
    PUBLIC=true; yesno "Dashboard öffentlich ohne Login?" "$( [ "$(cget dashboard.public)" = False ] && echo n || echo j)" || PUBLIC=false
    python3 - "$STANDALONE" "$LAN" "$SM_EMAIL" "$SM_PASS" "$HOST" "$FPORT" "$OEMAIL" "$OCALL" "$ONAME" "$TESTROOM" "$OTHERS" \
             "$DEFROOM" "$TITLE" "$PUBLIC" "$SA_USER" "$SA_PASS" > /tmp/frnadn-setup.json <<'EOF'
import json, sys
(sa_mode, lan, sm_email, sm_pass, host, port, oemail, ocall, oname, test, others, default, title, pub, su, sp) = sys.argv[1:17]
s = {"frn.standalone": sa_mode == "true", "frn.allow_lan": lan == "true", "sysman.email": sm_email.lower(), "frn.address": host,
     "frn.port": int(port or 10024), "frn.owner_email": oemail.lower() if oemail.lower() != sm_email.lower() else "",
     "frn.owner_callsign": ocall.upper(), "frn.owner_name": oname, "frn.default_room": default, "dashboard.title": title,
     "dashboard.public": pub == "true"}
if sm_pass:
    s["sysman.password"] = sm_pass
rooms = [x.strip() for x in others.split(",") if x.strip()]
print(json.dumps({"settings": s, "test_room": test, "rooms": rooms,
                  "superadmin": {"username": su, "password": sp} if su else {}}))
EOF
else
    python3 - "$SA_USER" "$SA_PASS" > /tmp/frnadn-setup.json <<'EOF'
import json, sys
print(json.dumps({"superadmin": {"username": sys.argv[1], "password": sys.argv[2]} if sys.argv[1] else {}}))
EOF
fi
umask 022
chown "$SVC_USER" /tmp/frnadn-setup.json
run_app apply-setup /tmp/frnadn-setup.json || { rm -f /tmp/frnadn-setup.json; fail "Einrichtung fehlgeschlagen"; }
rm -f /tmp/frnadn-setup.json
unset SA_PASS SA_REP SM_PASS
CUR="$(run_app show-settings 2>/dev/null || echo '{}')"
FPORT="$(cdef frn.port 10024)"

# ---------------------------------------------------------------------------
step 7 "Dienste frn-server und frnadn"
sed -e "s#/var/lib/frnadn/frn#${FRN_HOME}#g" -e "s#/opt/frn-server#${FRN_DIR}#g" -e "s#/usr/bin/java#${JAVA}#" \
    "$DIR/systemd/frn-server.service" > /etc/systemd/system/frn-server.service
sed -e "s#/opt/frnadn#${DIR}#g" -e "s#FRNADN_PORT=80#FRNADN_PORT=${PORT}#" -e "s#/var/lib/frnadn/frn#${FRN_HOME}#g" \
    -e "s#/opt/frn-server#${FRN_DIR}#g" "$DIR/systemd/frnadn.service" > /etc/systemd/system/frnadn.service
systemctl daemon-reload
systemctl enable -q frn-server frnadn
systemctl restart frn-server
systemctl restart frnadn
ok "frn-server und frnadn laufen und starten beim Booten"
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$PORT/tcp" >/dev/null; ufw allow "$FPORT/tcp" >/dev/null
    ok "Firewall (ufw): Port ${PORT} (Dashboard) und ${FPORT} (FRN) freigegeben"
fi

# ---------------------------------------------------------------------------
step 8 "Prüfen"
SLOG="$FRN_HOME/logs/server.log"
RESULT=""
for _ in $(seq 1 30); do
    sleep 1
    if [ -f "$SLOG" ]; then
        E="$(grep -o 'Error -[4-9].*' "$SLOG" 2>/dev/null | tail -1 || true)"
        if [ -n "$E" ]; then RESULT="error:$E"; break; fi
        if grep -q "server listening on port" "$SLOG" 2>/dev/null; then RESULT="ok"; break; fi
    fi
done
case "$RESULT" in
    ok)  ok "FRN-Server lauscht auf Port ${FPORT} – $(grep -o 'Java FRN_Server V [0-9.]* Build \[[0-9.]*\]' "$SLOG" | tail -1)" ;;
    error:*)
        warn "Der SystemManager meldet: ${RESULT#error:}"
        case "$RESULT" in
            *-4*) info "→ E-Mail oder Passwort des FRN-Kontos falsch: Admin-Portal → Settings → SystemManager" ;;
            *-5*) info "→ Server von außen nicht erreichbar: Serveradresse, Portweiterleitung TCP ${FPORT} und Firewall prüfen" ;;
            *-8*) info "→ Adresse und Port nutzt schon ein anderer FRN-Server" ;;
            *-9*) info "→ Dieses FRN-Konto ist schon mit einem anderen Server online" ;;
        esac
        info "Der Dienst versucht es jede Minute erneut; Log: journalctl -u frn-server -f" ;;
    *)   warn "Noch keine Rückmeldung vom FRN-Server – im Admin-Portal unter Logs nachsehen oder: journalctl -u frn-server -n 50" ;;
esac
if systemctl is-active -q frnadn; then ok "Dashboard läuft"; else warn "frnadn startet nicht: journalctl -u frnadn -n 50"; fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
SFX=""; [ "$PORT" != "80" ] && SFX=":$PORT"
echo -e "
${G}━━ ✅ Fertig!${N}
   Dashboard:     ${B}http://${IP}${SFX}${N}
   Admin-Portal:  Login oben rechts$( [ -n "$SA_USER" ] && echo " als ${B}${SA_USER}${N}")
   FRN-Server:    ${B}$(cget frn.address):${FPORT}${N} – Port ${FPORT}/TCP muss von außen erreichbar sein
   Konfiguration: in SQLite; der FRN-Server bekommt sie als ${FRN_HOME}/server.properties
   Befehle:       sudo frnadn reset-password NAME · journalctl -u frn-server -f · journalctl -u frnadn -f
"
