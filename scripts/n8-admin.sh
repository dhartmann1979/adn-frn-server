#!/usr/bin/env bash
# =============================================================================
#  N8 Admin – gemeinsamer Root-Helfer der N8schicht-Projekte (gleich in allen Repositorys)
#
#    n8-admin.sh check-perms [--json]   Berechtigungen und sudo prüfen, nichts ändern (Rückgabe 1 = Fehler)
#    n8-admin.sh fix-perms              prüfen → gezielt korrigieren (auch sudo) → erneut prüfen
#    n8-admin.sh sudo-setup             sudo-Freigaben fürs Webinterface schreiben (mit visudo geprüft)
#    n8-admin.sh update [--auto]        neue Version holen (nur vorspulen), Abhängigkeiten, Rechte, Neustart,
#                                       Prüfung der Weboberfläche – sonst zurück auf den alten Stand
#    n8-admin.sh setup-units            Update-Auslöser <id>-update.path/.service (und Keep-Alive) einrichten
#    n8-admin.sh setup-keepalive        nur den Keep-Alive-Timer <id>-keepalive.timer einrichten
#    n8-admin.sh keepalive              eine Runde Keep-Alive (läuft jede Minute per Timer)
#
#  Projektdaten stehen in n8-admin.conf neben diesem Skript (Name, Dienste, Datenordner, Hooks: n8_layout, n8_version,
#  n8_post_update, n8_sudo_extra, n8_restart, n8_check_extra, n8_fix_extra).
#  Aus dem Webinterface kommt der Aufruf per sudo aus der Sandbox des Dienstes (ProtectSystem: /etc schreibgeschützt);
#  dann startet sich das Skript als kurzlebiger systemd-Dienst außerhalb der Sandbox neu.
# =============================================================================
set -euo pipefail
export LC_ALL=C.UTF-8 2>/dev/null || export LC_ALL=C
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SELF")"
CONF="$HERE/n8-admin.conf"
[[ -f "$CONF" ]] || { echo "n8-admin.conf fehlt neben $SELF" >&2; exit 2; }

if [[ -t 1 ]]; then B=$'\e[1m'; R0=$'\e[0m'; G=$'\e[38;5;77m'; Y=$'\e[38;5;221m'; E=$'\e[38;5;203m'; C=$'\e[38;5;81m'
else B=""; R0=""; G=""; Y=""; E=""; C=""; fi
ok()   { echo "  ${G}✔${R0} $*"; }
warn() { echo "  ${Y}⚠${R0} $*"; }
info() { echo "  ${C}›${R0} $*"; }
fail() { echo "  ${E}✖ $*${R0}" >&2; exit 1; }

# ---------------------------------------------------------------- Projekt
# Vorgaben – n8-admin.conf überschreibt sie und kann n8_layout / n8_post_update / n8_sudo_extra definieren
N8_ID=""; N8_NAME=""; N8_MAIN_UNIT=""; N8_UNITS=(); N8_DATA_DIRS=(); N8_SECRETS=(); N8_GROUPS=(); N8_HEALTH_URL=""
N8_WRITABLE_IN_APP=(); N8_EXTRA_OWNED=(); N8_DATA_MODE=750; N8_RESTART_UNITS=()
# Keep-Alive: Prüfungen „Unit|Art|Ziel|Bezeichnung“ (Art: http = URL antwortet, tcp = host:port nimmt an, fn = Funktion aus der .conf,
# health = Punkt aus /api/n8/health der Anwendung („URL#punkt“, z. B. Verbindung des Protokolls), unit = nur „läuft“), Dienste mit Verbindungen nach draußen (nach einem Internet-Ausfall neu starten), Gegenstellen fürs Internet
N8_KA_CHECKS=(); N8_KA_NET_UNITS=(); N8_KA_NET_HOSTS="1.1.1.1:443 9.9.9.9:443 github.com:443"
N8_KA_FAILS=3        # so viele Minuten hintereinander krank → Neustart
N8_KA_MAX_HOUR=4     # höchstens so viele Neustarts je Dienst und Stunde (gegen Neustart-Schleifen)
N8_WEB_UNIT=""      # Dienst des Webinterfaces – muss sudo dürfen (NoNewPrivileges=no); leer = N8_MAIN_UNIT
N8_APP_GROUP=root   # Gruppe des Programmverzeichnisses (z. B. die des Dienstes, wenn „andere“ gar nichts lesen sollen)
APP=""; SVC_USER=""; STATE_DIR=""
n8_layout() { :; }; n8_post_update() { :; }; n8_sudo_extra() { :; }; n8_check_extra() { :; }; n8_fix_extra() { :; }; n8_restart() { local u; for u in "${N8_RESTART_UNITS[@]}"; do systemctl restart "$u" || true; done; }
# shellcheck source=/dev/null
. "$CONF"
unit_val() { sed -n "s/^$2=//p" "/etc/systemd/system/$1" 2>/dev/null | head -1; }
[[ -n "$APP" ]] || APP="$(unit_val "$N8_MAIN_UNIT" WorkingDirectory)"; [[ -n "$APP" ]] || APP="$(dirname "$HERE")"
[[ -n "$SVC_USER" ]] || SVC_USER="$(unit_val "$N8_MAIN_UNIT" User)"; [[ -n "$SVC_USER" ]] || SVC_USER="$N8_ID"
n8_layout
[[ -n "$N8_WEB_UNIT" ]] || N8_WEB_UNIT="$N8_MAIN_UNIT"
[[ -n "$STATE_DIR" ]] || STATE_DIR="${N8_DATA_DIRS[0]:-$APP/data}"
SUDOERS="/etc/sudoers.d/${N8_ID}-n8admin"
ADMIN_JSON="$STATE_DIR/n8-admin.json"
UPD_PATH="${N8_ID}-update.path"; UPD_SVC="${N8_ID}-update.service"
KA_TIMER="${N8_ID}-keepalive.timer"; KA_SVC="${N8_ID}-keepalive.service"

# ---------------------------------------------------------------- Sandbox des Dienstes verlassen
case "${1:-}" in
  check-perms|fix-perms|sudo-setup|update|setup-units|setup-keepalive)
    if [[ $EUID -eq 0 && -z "${N8_UNSANDBOXED:-}" && ! -w /etc ]]; then
      command -v systemd-run >/dev/null 2>&1 || fail "/etc ist schreibgeschützt (Dienst-Sandbox) und systemd-run fehlt"
      exec systemd-run --quiet --wait --pipe --collect --service-type=exec -p "Description=$N8_NAME – n8-admin $1" \
        --setenv=N8_UNSANDBOXED=1 -- "$SELF" "$@"
    fi ;;
esac

# ---------------------------------------------------------------- sudo-Freigaben
sudo_rules() {   # sudo_rules DATEI – schreibt die Freigaben, setzt UNITS_JSON
  local out="$1" SC ent u label acts a sep="" al
  SC=$(type -P systemctl || echo /usr/bin/systemctl); UNITS_JSON=""
  {
    echo "# $N8_NAME – von n8-admin.sh erzeugt, nicht von Hand ändern (wird bei jedem Update neu geschrieben)"
    echo "Defaults:$SVC_USER !requiretty"
    for ent in "${N8_UNITS[@]}"; do
      IFS='|' read -r u label acts <<<"$ent"; acts="${acts:-start stop restart enable disable}"
      for a in $acts; do
        case "$a" in start|restart) echo "$SVC_USER ALL=(root) NOPASSWD: $SC --no-block $a $u" ;;
                     *)             echo "$SVC_USER ALL=(root) NOPASSWD: $SC $a $u" ;; esac
      done
    done
    echo "$SVC_USER ALL=(root) NOPASSWD: $SC --no-block start $UPD_SVC"
    echo "$SVC_USER ALL=(root) NOPASSWD: $SELF check-perms --json"
    echo "$SVC_USER ALL=(root) NOPASSWD: $SELF fix-perms"
    n8_sudo_extra "$SC"
  } > "$out"
  for ent in "${N8_UNITS[@]}"; do
    IFS='|' read -r u label acts <<<"$ent"; acts="${acts:-start stop restart enable disable}"
    al=$(printf '"%s",' $acts); al="[${al%,}]"
    UNITS_JSON+="${sep}{\"unit\": \"$u\", \"label\": \"$label\", \"actions\": $al}"; sep=", "
  done
  SC_PATH="$SC"
}
admin_json() {
  printf '{"version": 1, "name": "%s", "id": "%s", "systemctl": "%s", "self": "%s", "update_unit": "%s", "request": "%s", "log": "%s", "result": "%s", "units": [%s]}\n' \
    "$N8_NAME" "$N8_ID" "$SC_PATH" "$SELF" "$UPD_SVC" "$STATE_DIR/update.request" "$STATE_DIR/update.log" "$STATE_DIR/update.result" "$UNITS_JSON"
}
includedir_ok() { grep -Eq '^[[:space:]]*[@#]includedir[[:space:]]+/etc/sudoers\.d[[:space:]]*$' /etc/sudoers 2>/dev/null; }
sudo_setup() {
  local T; T=$(mktemp)
  command -v sudo >/dev/null || { info "sudo fehlt – wird installiert"; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo >/dev/null 2>&1 || warn "sudo nicht installierbar"; }
  command -v sudo >/dev/null || { rm -f "$T"; return 0; }
  if [[ -f /etc/sudoers ]] && ! includedir_ok; then
    cat /etc/sudoers > "$T"; echo "@includedir /etc/sudoers.d" >> "$T"
    if visudo -cf "$T" >/dev/null 2>&1; then install -o root -g root -m 0440 "$T" /etc/sudoers; warn "/etc/sudoers band /etc/sudoers.d nicht ein – ergänzt"; fi
  fi
  install -d -o root -g root -m 0750 /etc/sudoers.d
  sudo_rules "$T"
  if visudo -cf "$T" >/dev/null 2>&1; then
    install -o root -g root -m 0440 "$T" "$SUDOERS"
    mkdir -p "$STATE_DIR"; admin_json > "$ADMIN_JSON"
    id "$SVC_USER" &>/dev/null && chown "$SVC_USER:$SVC_USER" "$ADMIN_JSON"; chmod 640 "$ADMIN_JSON"
    ok "sudo fürs Webinterface eingerichtet ($(grep -c NOPASSWD "$SUDOERS") freigegebene Befehle, mit visudo geprüft)"
  else
    warn "sudoers-Datei ungültig – nicht übernommen"; visudo -cf "$T" || true
  fi
  rm -f "$T"
}

# ---------------------------------------------------------------- Update-Auslöser (systemd)
setup_units() {
  cat > "/etc/systemd/system/$UPD_PATH" <<EOF
[Unit]
Description=$N8_NAME – Update aus dem Webinterface (Auslöser)

[Path]
PathExists=$STATE_DIR/update.request
Unit=$UPD_SVC

[Install]
WantedBy=multi-user.target
EOF
  cat > "/etc/systemd/system/$UPD_SVC" <<EOF
[Unit]
Description=$N8_NAME – Update ausführen (ausgelöst aus dem Webinterface)
After=network-online.target

[Service]
Type=oneshot
ExecStart=$SELF update --auto
TimeoutStartSec=1800
EOF
  chmod 644 "/etc/systemd/system/$UPD_PATH" "/etc/systemd/system/$UPD_SVC"
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable --now "$UPD_PATH" >/dev/null 2>&1 || true
  ok "„Update jetzt“ im Webinterface eingerichtet ($UPD_PATH)"
  setup_keepalive
}
setup_keepalive() {   # Keep-Alive: jede Minute als root (systemd-Timer)
  ((${#N8_KA_CHECKS[@]})) || return 0
  cat > "/etc/systemd/system/$KA_TIMER" <<EOF
[Unit]
Description=$N8_NAME – Keep-Alive (jede Minute)

[Timer]
OnBootSec=90
OnUnitActiveSec=60
AccuracySec=5
Unit=$KA_SVC

[Install]
WantedBy=timers.target
EOF
  cat > "/etc/systemd/system/$KA_SVC" <<EOF
[Unit]
Description=$N8_NAME – Keep-Alive: Dienste, Netz und Heartbeat prüfen
After=network-online.target

[Service]
Type=oneshot
ExecStart=$SELF keepalive
TimeoutStartSec=120
EOF
  chmod 644 "/etc/systemd/system/$KA_TIMER" "/etc/systemd/system/$KA_SVC"
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable --now "$KA_TIMER" >/dev/null 2>&1 || true
  ok "Keep-Alive eingerichtet ($KA_TIMER, jede Minute)"
}

# ---------------------------------------------------------------- Prüfung (ändert nichts)
CK=()
ck() { CK+=("$1|$2|$3"); }
ck_mode() {   # ck_mode Bereich Pfad besitzer:gruppe modus Text
  local is; is=$(stat -c '%U:%G %a' "$2" 2>/dev/null) || { ck bad "$1" "$5 fehlt ($2)"; return; }
  [[ "$is" == "$3 $4" ]] && ck ok "$1" "$5 ($3, $4)" || ck bad "$1" "$5: $is statt $3 $4 ($2)"
}
prune_args() {   # find-Ausschlüsse: beschreibbare Ordner im Programmverzeichnis
  local d; PRUNE=(); for d in "${N8_DATA_DIRS[@]}" "${N8_WRITABLE_IN_APP[@]}"; do [[ "$d" == "$APP"/* ]] && PRUNE+=(-path "$d" -prune -o); done
  return 0   # set -e: sonst beendet der letzte nicht passende Ordner das ganze Skript (fix-perms brach nach „korrigiere …“ ab)
}
check_perms() {
  local -; set +e +o pipefail
  CK=()
  local n x d f g first
  if id "$SVC_USER" &>/dev/null; then
    ck ok user "Dienstbenutzer $SVC_USER vorhanden"
    for g in "${N8_GROUPS[@]}"; do
      getent group "$g" >/dev/null || continue
      id -nG "$SVC_USER" | grep -qw "$g" && ck ok user "$SVC_USER in Gruppe $g" || ck bad user "$SVC_USER ist nicht in Gruppe $g"
    done
    x=$(getent passwd "$SVC_USER" | cut -d: -f7)
    if [[ "$x" == */nologin || "$x" == /bin/false ]]; then ck ok user "$SVC_USER hat keine Login-Shell"
    elif (( $(id -u "$SVC_USER") >= 1000 )); then ck ok user "$SVC_USER ist ein normaler Benutzer mit Shell ($x) – gewollt, der Dienst läuft unter deinem Konto"
    else ck warn user "$SVC_USER hat eine Login-Shell ($x)"; fi
  else ck bad user "Dienstbenutzer $SVC_USER fehlt – bitte den Installer neu starten"; fi
  [[ -d "$APP" ]] || { ck bad prog "$APP fehlt"; return 0; }
  prune_args
  n=$(find "$APP" "${PRUNE[@]}" ! -type l \( ! -user root -o ! -group "$N8_APP_GROUP" -o -perm /022 \) -print 2>/dev/null | wc -l)
  first=$(find "$APP" "${PRUNE[@]}" ! -type l \( ! -user root -o ! -group "$N8_APP_GROUP" -o -perm /022 \) -print 2>/dev/null | head -1)
  (( n == 0 )) && ck ok prog "Programm $APP gehört root und ist für den Dienst schreibgeschützt" \
               || ck bad prog "$n Programmdateien gehören nicht root:$N8_APP_GROUP oder sind beschreibbar (z. B. ${first#$APP/})"
  for f in "$SELF" "$APP"/scripts/*.sh "$APP"/*.sh; do [[ -f "$f" ]] && [[ "$(stat -c %a "$f")" != 755 ]] && ck bad prog "${f#$APP/} nicht 755"; done
  [[ "$(stat -c '%U %a' "$SELF")" == "root 755" ]] && ck ok prog "n8-admin.sh gehört root (755)" || ck bad prog "n8-admin.sh: $(stat -c '%U %a' "$SELF") statt root 755"
  if [[ -d "$APP/venv" ]]; then [[ -x "$APP/venv/bin/python" ]] && ck ok prog "Python-Umgebung (venv) ausführbar" || ck bad prog "venv/bin/python fehlt"; fi
  for d in "${N8_DATA_DIRS[@]}" "${N8_WRITABLE_IN_APP[@]}" "${N8_EXTRA_OWNED[@]}"; do
    [[ -e "$d" ]] || { [[ " ${N8_DATA_DIRS[*]} " == *" $d "* ]] && ck bad data "Datenordner $d fehlt"; continue; }
    n=$(find "$d" ! -user "$SVC_USER" ! -name update.log ! -name update.result -print 2>/dev/null | wc -l)
    (( n == 0 )) && ck ok data "$d gehört $SVC_USER" || ck bad data "$n Dateien in $d gehören nicht $SVC_USER"
  done
  for d in "${N8_DATA_DIRS[@]}"; do [[ -d "$d" ]] && { [[ "$(stat -c %a "$d")" == "$N8_DATA_MODE" ]] && ck ok data "$d ist $N8_DATA_MODE" || ck bad data "$d ist $(stat -c %a "$d") statt $N8_DATA_MODE"; }; done
  for g in "${N8_SECRETS[@]}"; do   # „Pfad-Muster|Modus“
    IFS='|' read -r x f <<<"$g"
    n=0; for d in $x; do [[ -f "$d" ]] && [[ "$(stat -c %a "$d")" != "$f" ]] && n=$((n + 1)); done
    (( n == 0 )) && ck ok data "geschützte Dateien ${x##*/} ($f)" || ck bad data "$n geschützte Dateien (${x##*/}) nicht $f – enthalten Zugangsdaten"
  done
  local ent u label
  for ent in "${N8_UNITS[@]}"; do
    IFS='|' read -r u label _ <<<"$ent"
    [[ "$u" == *.path || "$u" == "$UPD_SVC" ]] && continue
    if [[ -f "/etc/systemd/system/$u" ]]; then
      ck_mode systemd "/etc/systemd/system/$u" root:root 644 "$u"
      x=$(unit_val "$u" User); [[ -z "$x" || "$x" == root ]] && [[ " ${N8_ROOT_UNITS:-} " != *" $u "* ]] && ck warn systemd "$u läuft als root"
    elif systemctl cat "$u" >/dev/null 2>&1; then ck ok systemd "$u (aus einem Systempaket)"
    else ck warn systemd "$u ist nicht installiert"; fi
  done
  if [[ -f "/etc/systemd/system/$UPD_PATH" && -f "/etc/systemd/system/$UPD_SVC" ]]; then
    systemctl is-enabled "$UPD_PATH" >/dev/null 2>&1 && ck ok systemd "„Update jetzt“ ($UPD_PATH) aktiv" || ck bad systemd "$UPD_PATH ist nicht aktiv – „Update jetzt“ im Webinterface geht nicht"
    grep -qF "ExecStart=$SELF update --auto" "/etc/systemd/system/$UPD_SVC" && ck ok systemd "$UPD_SVC ruft n8-admin.sh auf" || ck bad systemd "$UPD_SVC veraltet"
  else ck bad systemd "Update-Auslöser $UPD_PATH fehlt"; fi
  if ((${#N8_KA_CHECKS[@]})); then
    if [[ -f "/etc/systemd/system/$KA_TIMER" ]] && grep -qF "ExecStart=$SELF keepalive" "/etc/systemd/system/$KA_SVC" 2>/dev/null; then
      systemctl is-enabled "$KA_TIMER" >/dev/null 2>&1 && ck ok systemd "Keep-Alive ($KA_TIMER) aktiv" || ck bad systemd "Keep-Alive ($KA_TIMER) ist nicht aktiv"
    else ck bad systemd "Keep-Alive ($KA_TIMER) fehlt oder ist veraltet"; fi
  fi
  if [[ -f "/etc/systemd/system/$N8_WEB_UNIT" ]]; then
    x=$(systemctl show -p NoNewPrivileges --value "$N8_WEB_UNIT" 2>/dev/null)
    [[ -z "$x" ]] && x=$(cat "/etc/systemd/system/$N8_WEB_UNIT" "/etc/systemd/system/$N8_WEB_UNIT.d/"*.conf 2>/dev/null | sed -n 's/^NoNewPrivileges=//p' | tail -1)
    [[ "$x" == yes || "$x" == true ]] && ck bad systemd "$N8_WEB_UNIT hat NoNewPrivileges=yes – das Webinterface kann sudo nicht nutzen" \
                                    || ck ok systemd "$N8_WEB_UNIT darf sudo nutzen (nur die Freigaben)"
    # eine enge CapabilityBoundingSet (z. B. nur CAP_NET_BIND_SERVICE) nimmt auch sudo die Rechte, die Nutzer-ID zu wechseln
    x=$(systemctl show -p CapabilityBoundingSet --value "$N8_WEB_UNIT" 2>/dev/null)
    [[ -z "$x" ]] && x=$(cat "/etc/systemd/system/$N8_WEB_UNIT" "/etc/systemd/system/$N8_WEB_UNIT.d/"*.conf 2>/dev/null | sed -n 's/^CapabilityBoundingSet=//p' | tail -1)
    if [[ -n "$x" && "$x" != "~" && "${x,,}" != *cap_setuid* ]]; then ck bad systemd "$N8_WEB_UNIT: CapabilityBoundingSet=$x – sudo kann so nicht arbeiten (NoNewPrivileges=yes)"; fi
    # die Unit kann stimmen, der laufende Prozess aber noch mit den alten Einstellungen gestartet sein
    x=$(systemctl show -p MainPID --value "$N8_WEB_UNIT" 2>/dev/null)
    if [[ -n "$x" && "$x" != 0 && -r "/proc/$x/status" ]]; then
      if grep -q '^NoNewPrivs:[[:space:]]*1' "/proc/$x/status"; then
        [[ "${WEB_RESTART_PLANNED:-0}" == 1 ]] && ck warn systemd "$N8_WEB_UNIT läuft noch mit NoNewPrivileges – Neustart ist eingeplant (in 5 s)" \
                                              || ck bad systemd "$N8_WEB_UNIT läuft noch mit NoNewPrivileges (vor der Korrektur gestartet) – sudo geht erst nach einem Neustart"
      else ck ok systemd "$N8_WEB_UNIT läuft ohne NoNewPrivileges"; fi
    fi
  fi
  if [[ -n "$(git -C "$APP" rev-parse --git-dir 2>/dev/null)" ]]; then   # git lehnt fremde Ordner ab („dubious ownership“) – der Dienst liest Version und Commit
    git config --system --get-all safe.directory 2>/dev/null | grep -qxF "$APP" && ck ok prog "git darf den Programmordner für alle Benutzer lesen (safe.directory)" \
      || ck bad prog "git: Programmordner nicht als sicher eingetragen – der Dienst sieht Commit und Updates nicht (safe.directory)"
  fi
  check_sudo
  n8_check_extra     # projekteigene Prüfungen (z. B. Modem-Schnittstelle), melden mit: ck ok|warn|bad Bereich Text
  return 0
}
web_unit_dropin() {   # NoNewPrivileges für das Webinterface aus – sudo erlaubt dann genau die Freigaben, sonst nichts
  [[ -f "/etc/systemd/system/$N8_WEB_UNIT" ]] || return 0
  install -d -m 755 "/etc/systemd/system/$N8_WEB_UNIT.d"
  printf '%s\n' "# $N8_NAME – von n8-admin.sh: das Webinterface nutzt sudo (nur die Befehle in $SUDOERS)" "[Service]" "NoNewPrivileges=no" "CapabilityBoundingSet=~" \
    > "/etc/systemd/system/$N8_WEB_UNIT.d/n8-admin.conf"
  chmod 644 "/etc/systemd/system/$N8_WEB_UNIT.d/n8-admin.conf"
  systemctl daemon-reload >/dev/null 2>&1 || true
  warn "$N8_WEB_UNIT: NoNewPrivileges aus (Drop-in n8-admin.conf) – wirkt nach dem nächsten Neustart des Dienstes"
}
web_restart_if_needed() {   # läuft das Webinterface noch mit NoNewPrivileges, in 5 s neu starten (auch wenn der Aufruf aus ihm selbst kommt)
  local pid; pid=$(systemctl show -p MainPID --value "$N8_WEB_UNIT" 2>/dev/null || true)
  [[ -n "$pid" && "$pid" != 0 && -r "/proc/$pid/status" ]] || return 0
  grep -q '^NoNewPrivs:[[:space:]]*1' "/proc/$pid/status" || return 0
  if systemd-run --quiet --on-active=5 --collect -p "Description=$N8_NAME – Webinterface ohne NoNewPrivileges neu starten" \
       "$(type -P systemctl || echo /usr/bin/systemctl)" restart "$N8_WEB_UNIT" >/dev/null 2>&1; then
    WEB_RESTART_PLANNED=1; info "$N8_WEB_UNIT startet in 5 s neu (danach darf es sudo nutzen)"
  else systemctl --no-block restart "$N8_WEB_UNIT" || true; WEB_RESTART_PLANNED=1; fi
  return 0
}
check_sudo() {
  local -; set +e +o pipefail
  local T x
  command -v sudo >/dev/null || { ck bad sudo "sudo ist nicht installiert – Dienste und Updates im Webinterface gehen nicht"; return 0; }
  ck ok sudo "sudo installiert"
  command -v systemd-run >/dev/null && ck ok sudo "systemd-run vorhanden (Root-Aufgaben laufen außerhalb der Dienst-Sandbox)" || ck bad sudo "systemd-run fehlt"
  [[ -w /etc ]] && ck ok sudo "/etc beschreibbar (Prüfung läuft außerhalb der Sandbox)" || ck bad sudo "/etc ist hier schreibgeschützt – Prüfung läuft noch in der Dienst-Sandbox"
  includedir_ok && ck ok sudo "/etc/sudoers bindet /etc/sudoers.d ein" || ck bad sudo "/etc/sudoers bindet /etc/sudoers.d nicht ein – die Freigaben wirken nicht"
  [[ -f "$SUDOERS" ]] || { ck bad sudo "Freigaben $SUDOERS fehlen"; return 0; }
  ck_mode sudo "$SUDOERS" root:root 440 "Freigaben $SUDOERS"
  visudo -cf "$SUDOERS" >/dev/null 2>&1 && ck ok sudo "Freigaben gültig (visudo)" || ck bad sudo "Freigaben ungültig (visudo)"
  T=$(mktemp); sudo_rules "$T"
  x=$(diff <(grep -v '^#' "$T" | sort) <(grep -v '^#' "$SUDOERS" | sort) | grep -c '^[<>]'); rm -f "$T"
  [[ "$x" == 0 ]] && ck ok sudo "Freigaben aktuell ($(grep -c NOPASSWD "$SUDOERS") Befehle)" || ck bad sudo "Freigaben veraltet oder von Hand geändert ($x Zeilen weichen ab)"
  if id "$SVC_USER" &>/dev/null && sudo -l -U "$SVC_USER" 2>/dev/null | grep -qF "$SELF fix-perms"; then ck ok sudo "Freigaben wirksam für $SVC_USER (sudo -l)"
  else ck bad sudo "Freigaben wirken nicht für $SVC_USER (sudo -l)"; fi
  if [[ -f "$ADMIN_JSON" ]]; then
    ck_mode sudo "$ADMIN_JSON" "$SVC_USER:$SVC_USER" 640 "n8-admin.json (was das Webinterface darf)"
    T=$(mktemp); sudo_rules "$T"; rm -f "$T"
    [[ "$(admin_json)" == "$(cat "$ADMIN_JSON")" ]] && ck ok sudo "n8-admin.json aktuell" || ck bad sudo "n8-admin.json veraltet"
  else ck bad sudo "n8-admin.json fehlt – das Webinterface weiß nicht, was es darf"; fi
  return 0
}
perm_bad() { local l n=0; for l in "${CK[@]}"; do [[ "$l" == bad\|* ]] && n=$((n + 1)); done; echo "$n"; }
perm_bad_in() { local l; for l in "${CK[@]}"; do [[ "$l" == "bad|$1|"* ]] && return 0; done; return 1; }
perm_report() {
  local l st ar tx last="" icon
  declare -A NAME=([user]="Dienstbenutzer" [prog]="Programm $APP" [data]="Daten" [systemd]="systemd" [sudo]="sudo" [hw]="Hardware")
  for l in "${CK[@]}"; do
    IFS='|' read -r st ar tx <<<"$l"
    [[ "${1:-alle}" == fehler && "$st" == ok ]] && continue
    [[ "$ar" != "$last" ]] && { echo "  ${B}${NAME[$ar]:-$ar}${R0}"; last="$ar"; }
    case "$st" in ok) icon="${G}✔${R0}" ;; warn) icon="${Y}⚠${R0}" ;; *) icon="${E}✖${R0}" ;; esac
    echo "    $icon $tx"
  done
}
perm_json() {
  printf '%s\n' "${CK[@]}" | python3 -c 'import json,sys
rows = [dict(zip(("status", "area", "text"), l.rstrip("\n").split("|", 2))) for l in sys.stdin if l.strip()]
print(json.dumps({"ok": not any(r["status"] == "bad" for r in rows), "bad": sum(r["status"] == "bad" for r in rows),
                  "warn": sum(r["status"] == "warn" for r in rows), "checks": rows}, ensure_ascii=False))'
}

# ---------------------------------------------------------------- Korrektur
fix_perms() {
  local d g x f
  prune_args
  find "$APP" "${PRUNE[@]}" ! -type l \( ! -user root -o ! -group "$N8_APP_GROUP" \) -exec chown -h "root:$N8_APP_GROUP" {} + 2>/dev/null || true
  find "$APP" "${PRUNE[@]}" ! -type l -perm /022 -exec chmod go-w {} + 2>/dev/null || true
  chown "root:$N8_APP_GROUP" "$SELF"; chmod 755 "$SELF"
  for f in "$APP"/scripts/*.sh "$APP"/*.sh; do [[ -f "$f" ]] && chmod 755 "$f"; done
  if id "$SVC_USER" &>/dev/null; then
    for g in "${N8_GROUPS[@]}"; do getent group "$g" >/dev/null && ! id -nG "$SVC_USER" | grep -qw "$g" && usermod -aG "$g" "$SVC_USER"; done
    for d in "${N8_DATA_DIRS[@]}"; do install -d -o "$SVC_USER" -g "$SVC_USER" -m "$N8_DATA_MODE" "$d"; done
    for d in "${N8_DATA_DIRS[@]}" "${N8_WRITABLE_IN_APP[@]}" "${N8_EXTRA_OWNED[@]}"; do [[ -e "$d" ]] && chown -R "$SVC_USER:$SVC_USER" "$d"; done
    for d in "${N8_DATA_DIRS[@]}"; do chmod "$N8_DATA_MODE" "$d"; done
    for d in "$STATE_DIR/update.log" "$STATE_DIR/update.result"; do [[ -f "$d" ]] && chown root:root "$d" && chmod 644 "$d"; done
  fi
  for g in "${N8_SECRETS[@]}"; do IFS='|' read -r x f <<<"$g"; for d in $x; do [[ -f "$d" ]] && chmod "$f" "$d"; done; done
  local ent u
  for ent in "${N8_UNITS[@]}"; do IFS='|' read -r u _ <<<"$ent"; [[ -f "/etc/systemd/system/$u" ]] && chown root:root "/etc/systemd/system/$u" && chmod 644 "/etc/systemd/system/$u"; done
  if [[ -n "$(git -C "$APP" rev-parse --git-dir 2>/dev/null)" ]]; then
    git config --system --get-all safe.directory 2>/dev/null | grep -qxF "$APP" || git config --system --add safe.directory "$APP" 2>/dev/null || true
    git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$APP" || git config --global --add safe.directory "$APP" 2>/dev/null || true
  fi
  n8_fix_extra || true   # projekteigene Korrekturen
  return 0
}
repair() {
  local before after
  check_perms; before=$(perm_bad)
  if (( before == 0 )); then ok "Berechtigungen und sudo geprüft – ${#CK[@]} Prüfungen, alles in Ordnung"; perm_report fehler; return 0; fi
  warn "$before Fehler gefunden:"; perm_report fehler
  info "korrigiere …"
  fix_perms
  perm_bad_in systemd && { setup_units; grep -q "NoNewPrivileges=yes" <<<"${CK[*]}" && web_unit_dropin; }
  perm_bad_in sudo && sudo_setup
  web_restart_if_needed
  check_perms; after=$(perm_bad)
  if (( after == 0 )); then ok "alle $before Fehler korrigiert – erneut geprüft, alles in Ordnung"; return 0; fi
  warn "$after Fehler ließen sich nicht automatisch korrigieren:"; perm_report fehler; return 1
}

# ---------------------------------------------------------------- Update
git_() { git -c "safe.directory=$APP" -c core.hooksPath=/dev/null -c protocol.ext.allow=never -C "$APP" "$@"; }
health() {   # Webinterface lebt? Jede HTTP-Antwort zählt (auch 301/401/403 – Weiterleitung auf HTTPS, Anmeldung nötig);
             # sonst: Dienst läuft und sein Prozess lauscht auf einem TCP-Port (Adresse/HTTPS/Port unbekannt). Bis zu 2 Minuten.
  local i u code pid
  for i in $(seq 1 60); do
    for u in $N8_HEALTH_URL; do
      code=$(curl -sk -m 3 -o /dev/null -w '%{http_code}' "$u" 2>/dev/null || true)
      [[ "$code" =~ ^[1-4][0-9][0-9]$ ]] && return 0
    done
    pid=$(systemctl show -p MainPID --value "$N8_WEB_UNIT" 2>/dev/null || true)
    if (( i > 5 )) && [[ -n "$pid" && "$pid" != 0 ]] && systemctl is-active -q "$N8_WEB_UNIT" 2>/dev/null \
       && ss -Hltnp 2>/dev/null | grep -q "pid=$pid,"; then return 0; fi
    sleep 2
  done
  return 1
}
result() {  # result ok from to message
  printf '{"ok": %s, "from": "%s", "to": "%s", "time": %s, "message": "%s"}\n' "$1" "$2" "$3" "$(date +%s)" "${4//\"/\'}" > "$STATE_DIR/update.result"
  chmod 644 "$STATE_DIR/update.result" 2>/dev/null || true
}
version_of() { n8_version 2>/dev/null || git_ describe --tags --always 2>/dev/null || echo "?"; }
do_update() {
  local auto="${1:-}" old new branch dirty old_ver new_ver
  mkdir -p "$STATE_DIR"
  if [[ "$auto" == --auto ]]; then
    rm -f "$STATE_DIR/update.request"
    exec > >(tee "$STATE_DIR/update.log") 2>&1
    chmod 644 "$STATE_DIR/update.log" 2>/dev/null || true
  fi
  echo "=== $N8_NAME: Update gestartet $(date '+%d.%m.%Y %H:%M:%S') ==="
  [[ -n "$(git_ rev-parse --git-dir 2>/dev/null)" ]] || { result false "?" "?" "kein git-Checkout in $APP"; fail "$APP ist kein git-Checkout"; }
  branch="$(git_ rev-parse --abbrev-ref HEAD)"; old="$(git_ rev-parse HEAD)"; old_ver="$(version_of)"
  info "Hole Updates ($branch) …"
  git_ fetch -q --no-tags origin "refs/heads/$branch" || { result false "$old_ver" "?" "git fetch fehlgeschlagen"; fail "git fetch fehlgeschlagen"; }
  dirty="$(git_ status --porcelain --untracked-files=no)"
  if [[ -n "$dirty" ]]; then
    result false "$old_ver" "?" "von Hand geänderte Dateien – Update abgebrochen"
    echo "$dirty" | head -10; fail "Im Programmverzeichnis wurden Dateien von Hand geändert – nichts aktualisiert (git status)"
  fi
  git_ merge -q --ff-only FETCH_HEAD || { result false "$old_ver" "?" "kein Vorspulen möglich (eigene Commits?)"; fail "Kein Vorspulen möglich – lokale Commits?"; }
  new="$(git_ rev-parse HEAD)"; new_ver="$(version_of)"
  info "Version: $old_ver → $new_ver"
  n8_post_update "$old" "$new" || warn "Nacharbeiten mit Fehler"
  fix_perms; setup_units >/dev/null; sudo_setup >/dev/null
  check_perms; grep -q "NoNewPrivileges=yes" <<<"${CK[*]}" && web_unit_dropin
  n8_restart
  if ! health; then
    if [[ "$old" != "$new" ]]; then
      warn "Version $new_ver antwortet nicht – zurück auf $old_ver (${old:0:7})"
      git_ update-index -q --refresh >/dev/null 2>&1 || true; rm -f "$APP/.git/index.lock"
      git_ reset -q --keep "$old" 2>/dev/null || git_ reset -q --hard "$old" || git_ checkout -q -f "$old" || warn "Zurücksetzen fehlgeschlagen – bitte auf der Konsole: git -C $APP reset --hard ${old:0:7}"
      n8_post_update "$new" "$old" || true; fix_perms; n8_restart
      health && info "$old_ver läuft wieder" || warn "auch $old_ver antwortet nicht"
    fi
    result false "$old_ver" "$new_ver" "zurückgesetzt auf $old_ver"
    echo "=== Update auf $new_ver fehlgeschlagen $(date '+%d.%m.%Y %H:%M:%S') ==="; exit 1
  fi
  check_perms; (( $(perm_bad) == 0 )) || { warn "Berechtigungen:"; perm_report fehler; }
  [[ "$old" != "$new" ]] && result true "$old_ver" "$new_ver" ""
  echo "=== Update fertig ($new_ver) $(date '+%d.%m.%Y %H:%M:%S') ==="
}

# ---------------------------------------------------------------- Keep-Alive (Timer jede Minute, als root)
# Prüft jeden Dienst wirklich (Antwort der Weboberfläche, offener Port, Verbindung des Protokolls), startet kranke Dienste neu
# (erst nach N8_KA_FAILS Minuten, höchstens N8_KA_MAX_HOUR mal je Stunde), erkennt Internet-Ausfälle und startet danach die
# Dienste mit Verbindungen nach draußen neu, und meldet sich bei einer Heartbeat-Adresse (Uptime Kuma, Healthchecks.io …).
# Einstellungen (vom Webinterface geschrieben, hier nur gelesen – nie ausgeführt): $STATE_DIR/keepalive.conf
# Zustand fürs Webinterface: $STATE_DIR/keepalive.json · Protokoll: $STATE_DIR/keepalive.log · Halt: $STATE_DIR/keepalive.hold/<unit>
ka_log() { local l; l="$(date '+%Y-%m-%d %H:%M:%S') $*"; echo "$l"; echo "$l" >> "$STATE_DIR/keepalive.log"; logger -t "$N8_ID-keepalive" -- "$*" 2>/dev/null || true; }
ka_conf() {   # ka_conf schlüssel vorgabe – nur erlaubte Zeichen, keine Shell
  local v; v="$(sed -n "s/^$1=//p" "$STATE_DIR/keepalive.conf" 2>/dev/null | tail -1 | tr -d '\r')"
  [[ "$v" =~ ^[A-Za-z0-9._~:/?#@!\&+,\;=%-]*$ ]] || v=""
  echo "${v:-$2}"
}
ka_tcp() { local h="${1%:*}" p="${1##*:}"; timeout 4 bash -c "exec 3<>/dev/tcp/$h/$p" 2>/dev/null; }
ka_http() { local c; c=$(curl -sk -m 8 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true); [[ "$c" =~ ^[1-4][0-9][0-9]$ ]]; }   # jede Antwort außer 5xx
declare -A KA_HEALTH=()
ka_health() {   # ka_health URL#punkt – /api/n8/health der Anwendung (nur von 127.0.0.1): {"items": {"punkt": {"ok": true, "why": "…"}}}
  local url="${1%%#*}" item="${1#*#}" body
  if [[ -z "${KA_HEALTH[$url]+x}" ]]; then KA_HEALTH[$url]="$(curl -fsSk -m 8 "$url" 2>/dev/null || echo '{"error": "keine Antwort"}')"; fi
  body="${KA_HEALTH[$url]}"
  python3 -c 'import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("Antwort ist kein JSON"); sys.exit(1)
if "items" not in d:
    print(d.get("error") or "keine Antwort"); sys.exit(1)
i = d["items"].get(sys.argv[2])
if i is None or i.get("ok", True):
    sys.exit(0)
print(i.get("why") or (sys.argv[2] + " nicht in Ordnung")); sys.exit(1)' "$body" "$item"
}
ka_net() { local h; for h in $N8_KA_NET_HOSTS; do ka_tcp "$h" && return 0; done; return 1; }
ka_json() {   # ka_json DATEI SCHLÜSSEL [WERT] – kleiner Zustandsspeicher „schlüssel=wert“ (reines bash, läuft jede Minute)
  local f="$1" k="$2" line out=""
  if (( $# > 2 )); then
    [[ -f "$f" ]] && while IFS= read -r line; do [[ "${line%%=*}" == "$k" ]] || out+="$line"$'\n'; done < "$f"
    printf '%s%s=%s\n' "$out" "$k" "$3" > "$f.tmp" && mv -f "$f.tmp" "$f"
  else
    [[ -f "$f" ]] && while IFS= read -r line; do [[ "${line%%=*}" == "$k" ]] && { echo "${line#*=}"; return 0; }; done < "$f"
    echo ""
  fi
}
do_keepalive() {
  local -; set +e +o pipefail
  mkdir -p "$STATE_DIR/keepalive.hold"; id "$SVC_USER" &>/dev/null && chown "$SVC_USER:$SVC_USER" "$STATE_DIR/keepalive.hold"
  local done_units=""
  local st="$STATE_DIR/keepalive.state" now ent u kind tgt label act healthy why fails last hour n rows="" sep="" allok=1 restarted=0
  now=$(date +%s)
  [[ "$(ka_conf enabled 1)" == 0 ]] && { ka_write "$now" "aus" ""; return 0; }
  local pause; pause=$(ka_conf paused_until 0); [[ "$pause" =~ ^[0-9]+$ ]] || pause=0
  # --- Internet
  local net=1 down_since back=""
  if ka_net; then
    down_since=$(ka_json "$st" net_down_since)
    if [[ -n "$down_since" ]]; then
      ka_json "$st" net_down_since "" >/dev/null
      back=$(( now - down_since ))
      ka_log "🌐 Internet wieder da (nach $back s Ausfall)"
      if (( back >= 60 )) && [[ "$(ka_conf net_restart 1)" == 1 ]] && (( now >= pause )); then
        for u in "${N8_KA_NET_UNITS[@]}"; do
          [[ -f "$STATE_DIR/keepalive.hold/$u" ]] && continue
          systemctl is-enabled "$u" >/dev/null 2>&1 || continue
          ka_log "↻ $u nach dem Internet-Ausfall neu gestartet"; systemctl restart "$u" >/dev/null 2>&1; restarted=$((restarted + 1)); done_units+=" $u "
        done
      fi
    fi
  else
    net=0; allok=0
    [[ -z "$(ka_json "$st" net_down_since)" ]] && { ka_json "$st" net_down_since "$now" >/dev/null; ka_log "🌐 Internet weg (keine Antwort von $N8_KA_NET_HOSTS)"; }
  fi
  # --- Dienste
  for ent in "${N8_KA_CHECKS[@]}"; do
    IFS='|' read -r u kind tgt label <<<"$ent"
    local ck="$u#$kind"     # Zähler je Prüfung (ein Dienst kann mehrere haben), Neustarts je Dienst
    act=$(systemctl is-active "$u" 2>/dev/null); healthy=1; why=""
    if [[ -f "$STATE_DIR/keepalive.hold/$u" ]]; then
      rows+="$sep{\"unit\": \"$u\", \"label\": \"${label:-$u}\", \"state\": \"hold\", \"active\": \"$act\", \"why\": \"von Hand gestoppt – Keep-Alive wartet\"}"; sep=", "; continue
    fi
    if [[ "$act" != active ]]; then healthy=0; why="Dienst $act"
    else
      case "$kind" in
        http) ka_http "$tgt" || { healthy=0; why="keine Antwort von $tgt"; } ;;
        tcp)  ka_tcp "$tgt" || { healthy=0; why="Port $tgt nimmt nichts an"; } ;;
        health) why="$(ka_health "$tgt" 2>&1)" && why="" || healthy=0 ;;
        fn)   why="$("$tgt" 2>&1)"; [[ $? == 0 ]] && why="" || { healthy=0; why="$(tail -1 <<<"$why")"; why="${why:-Prüfung $tgt fehlgeschlagen}"; } ;;
      esac
      # eine Verbindung nach draußen kann ohne Internet nicht stehen – dann nicht neu starten, nur melden
      if (( ! healthy && ! net )) && [[ " ${N8_KA_NET_UNITS[*]} " == *" $u "* ]]; then why="$why (Internet weg – kein Neustart)"; healthy=2; fi
    fi
    fails=$(ka_json "$st" "fails:$ck"); fails=${fails:-0}
    if (( healthy == 1 )); then
      (( fails > 0 )) && ka_log "✔ $u wieder gesund"
      ka_json "$st" "fails:$ck" 0 >/dev/null; fails=0
      rows+="$sep{\"unit\": \"$u\", \"label\": \"${label:-$u}\", \"state\": \"ok\", \"active\": \"$act\", \"why\": \"\", \"fails\": 0}"
    else
      allok=0; fails=$((fails + 1)); ka_json "$st" "fails:$ck" "$fails" >/dev/null
      (( fails == 1 )) && ka_log "⚠ $u: ${why//\"/\'}"
      local state=sick
      local crashed=0; [[ "$act" == failed ]] && crashed=1
      if [[ "$done_units" == *" $u "* ]]; then state=restarted
      elif (( healthy == 0 && (fails >= N8_KA_FAILS || crashed) )) && (( now >= pause )); then
        hour=$(ka_json "$st" "hour:$u"); n=$(ka_json "$st" "count:$u"); n=${n:-0}
        [[ -z "$hour" || $(( now - hour )) -ge 3600 ]] && { hour=$now; n=0; ka_json "$st" "hour:$u" "$now" >/dev/null; }
        if (( n < N8_KA_MAX_HOUR )); then
          ka_log "↻ $u neu gestartet ($why, seit $fails min)"; systemctl restart "$u" >/dev/null 2>&1
          ka_json "$st" "count:$u" $((n + 1)) >/dev/null; ka_json "$st" "fails:$ck" 0 >/dev/null; ka_json "$st" "last:$u" "$now" >/dev/null
          restarted=$((restarted + 1)); state=restarted; done_units+=" $u "
          last=$(ka_json "$st" "total:$u"); ka_json "$st" "total:$u" $(( ${last:-0} + 1 )) >/dev/null
        else
          state=giveup; (( fails == N8_KA_FAILS )) && ka_log "✖ $u: schon $N8_KA_MAX_HOUR Neustarts in dieser Stunde – Keep-Alive wartet (bitte nachsehen)"
        fi
      fi
      rows+="$sep{\"unit\": \"$u\", \"label\": \"${label:-$u}\", \"state\": \"$state\", \"active\": \"$act\", \"why\": \"${why//\"/\'}\", \"fails\": $fails}"
    fi
    last=$(ka_json "$st" "total:$u"); rows="${rows%\}}, \"restarts\": ${last:-0}, \"last_restart\": $(ka_json "$st" "last:$u" | sed 's/^$/0/')}"
    sep=", "
  done
  # --- Heartbeat
  local hb hbf hbres="" ; hb=$(ka_conf heartbeat_url ""); hbf=$(ka_conf heartbeat_fail_url "")
  if [[ "$hb" =~ ^https?:// ]]; then
    if (( allok )); then curl -fsS -m 10 -o /dev/null "$hb" 2>/dev/null && hbres=ok || hbres=fehler
    elif [[ "$hbf" =~ ^https?:// ]]; then curl -fsS -m 10 -o /dev/null "$hbf" 2>/dev/null && hbres=fail-gemeldet || hbres=fehler
    else hbres=ausgelassen; fi
  fi
  ka_write "$now" "$( (( now < pause )) && echo pausiert || echo an )" "$rows" "$net" "$hbres" "$restarted"
  # Protokoll kurz halten
  if [[ -f "$STATE_DIR/keepalive.log" ]] && (( $(wc -l < "$STATE_DIR/keepalive.log") > 600 )); then
    tail -400 "$STATE_DIR/keepalive.log" > "$STATE_DIR/keepalive.log.tmp" && mv -f "$STATE_DIR/keepalive.log.tmp" "$STATE_DIR/keepalive.log"
  fi
  chmod 644 "$STATE_DIR/keepalive.log" "$STATE_DIR/keepalive.json" 2>/dev/null; chmod 600 "$st" 2>/dev/null
  return 0
}
ka_write() {   # ka_write zeit modus zeilen [netz heartbeat neustarts]
  local ds; ds=$(ka_json "$STATE_DIR/keepalive.state" net_down_since)
  printf '{"time": %s, "mode": "%s", "net": %s, "net_down_since": %s, "heartbeat": "%s", "restarted": %s, "net_hosts": "%s", "fails_needed": %s, "max_hour": %s, "checks": [%s]}\n' \
    "$1" "$2" "${4:-1}" "${ds:-0}" "${5:-}" "${6:-0}" "$N8_KA_NET_HOSTS" "$N8_KA_FAILS" "$N8_KA_MAX_HOUR" "$3" > "$STATE_DIR/keepalive.json"
}

# ---------------------------------------------------------------- Aufruf
[[ $EUID -eq 0 ]] || fail "Bitte als root starten: sudo $SELF ${1:-}"
case "${1:-}" in
  check-perms)
    check_perms
    if [[ "${2:-}" == "--json" ]]; then perm_json
    else echo "Berechtigungen und sudo prüfen ($N8_NAME) …"; perm_report alle
      (( $(perm_bad) == 0 )) && ok "alles in Ordnung" || warn "$(perm_bad) Fehler – korrigieren: sudo $SELF fix-perms"; fi
    (( $(perm_bad) == 0 )); exit $? ;;
  fix-perms) echo "Berechtigungen und sudo prüfen & korrigieren ($N8_NAME) …"; repair; exit $? ;;
  sudo-setup) sudo_setup ;;
  setup-units) setup_units ;;
  setup-keepalive) setup_keepalive ;;
  keepalive) do_keepalive ;;
  update) do_update "${2:-}" ;;
  *) echo "Aufruf: $SELF check-perms [--json] | fix-perms | sudo-setup | setup-units | setup-keepalive | keepalive | update [--auto]"; exit 2 ;;
esac
