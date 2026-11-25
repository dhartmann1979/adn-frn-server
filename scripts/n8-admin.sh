#!/usr/bin/env bash
# =============================================================================
#  N8 Admin – gemeinsamer Root-Helfer der N8schicht-Projekte (gleich in allen Repositorys)
#
#    n8-admin.sh check-perms [--json]   Berechtigungen und sudo prüfen, nichts ändern (Rückgabe 1 = Fehler)
#    n8-admin.sh fix-perms              prüfen → gezielt korrigieren (auch sudo) → erneut prüfen
#    n8-admin.sh sudo-setup             sudo-Freigaben fürs Webinterface schreiben (mit visudo geprüft)
#    n8-admin.sh update [--auto]        neue Version holen (nur vorspulen), Abhängigkeiten, Rechte, Neustart,
#                                       Prüfung der Weboberfläche – sonst zurück auf den alten Stand
#    n8-admin.sh setup-units            Update-Auslöser <id>-update.path/.service einrichten
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

# ---------------------------------------------------------------- Sandbox des Dienstes verlassen
case "${1:-}" in
  check-perms|fix-perms|sudo-setup|update|setup-units)
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
    [[ "$x" == */nologin || "$x" == /bin/false ]] && ck ok user "$SVC_USER hat keine Login-Shell" || ck warn user "$SVC_USER hat eine Login-Shell ($x)"
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
  if [[ -f "/etc/systemd/system/$N8_WEB_UNIT" ]]; then
    x=$(systemctl show -p NoNewPrivileges --value "$N8_WEB_UNIT" 2>/dev/null)
    [[ -z "$x" ]] && x=$(cat "/etc/systemd/system/$N8_WEB_UNIT" "/etc/systemd/system/$N8_WEB_UNIT.d/"*.conf 2>/dev/null | sed -n 's/^NoNewPrivileges=//p' | tail -1)
    [[ "$x" == yes || "$x" == true ]] && ck bad systemd "$N8_WEB_UNIT hat NoNewPrivileges=yes – das Webinterface kann sudo nicht nutzen" \
                                    || ck ok systemd "$N8_WEB_UNIT darf sudo nutzen (nur die Freigaben)"
    # eine enge CapabilityBoundingSet (z. B. nur CAP_NET_BIND_SERVICE) nimmt auch sudo die Rechte, die Nutzer-ID zu wechseln
    x=$(systemctl show -p CapabilityBoundingSet --value "$N8_WEB_UNIT" 2>/dev/null)
    [[ -z "$x" ]] && x=$(cat "/etc/systemd/system/$N8_WEB_UNIT" "/etc/systemd/system/$N8_WEB_UNIT.d/"*.conf 2>/dev/null | sed -n 's/^CapabilityBoundingSet=//p' | tail -1)
    if [[ -n "$x" && "$x" != "~" && "${x,,}" != *cap_setuid* ]]; then ck bad systemd "$N8_WEB_UNIT: CapabilityBoundingSet=$x – sudo kann so nicht arbeiten (NoNewPrivileges=yes)"; fi
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
  [[ -n "$(git -C "$APP" rev-parse --git-dir 2>/dev/null)" ]] && git config --global --add safe.directory "$APP" 2>/dev/null || true
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
  check_perms; after=$(perm_bad)
  if (( after == 0 )); then ok "alle $before Fehler korrigiert – erneut geprüft, alles in Ordnung"; return 0; fi
  warn "$after Fehler ließen sich nicht automatisch korrigieren:"; perm_report fehler; return 1
}

# ---------------------------------------------------------------- Update
git_() { git -c "safe.directory=$APP" -c core.hooksPath=/dev/null -c protocol.ext.allow=never -C "$APP" "$@"; }
health() {   # Weboberfläche antwortet innerhalb von 90 s? (N8_HEALTH_URL: eine oder mehrere Adressen, Leerzeichen getrennt)
  [[ -z "$N8_HEALTH_URL" ]] && return 0
  local i u; for i in $(seq 1 45); do
    for u in $N8_HEALTH_URL; do curl -fsSk -m 3 -o /dev/null "$u" 2>/dev/null && return 0; done   # mehrere Adressen möglich (http/https)
    sleep 2; done; return 1
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
      git_ reset -q --keep "$old" || git_ reset -q --hard "$old"
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
  update) do_update "${2:-}" ;;
  *) echo "Aufruf: $SELF check-perms [--json] | fix-perms | sudo-setup | setup-units | update [--auto]"; exit 2 ;;
esac
