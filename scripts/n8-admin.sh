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
#    n8-admin.sh setup-crashwatch       Absturz-Wächter: systemd-Drop-in (ExecStopPost) für jeden Dienst des Projekts
#    n8-admin.sh crash-hook UNIT        läuft nach JEDEM Ende eines Dienstes (vom Drop-in, als root) und hält Abstürze fest
#    n8-admin.sh crashes                die letzten Befunde auf der Konsole anzeigen
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
# Absturz-Wächter: überwachte Dienste (leer = Hauptdienst + N8_UNITS + Dienste der Keep-Alive-Prüfungen, nur *.service),
# so viele Befunde bleiben in $STATE_DIR/crashes.jsonl (Einzelheiten in $STATE_DIR/crash/<id>.log)
N8_CRASH_UNITS=(); N8_CRASH_KEEP=300
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
  check-perms|fix-perms|sudo-setup|update|setup-units|setup-keepalive|setup-crashwatch)
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
setup_keepalive() {   # Keep-Alive: jede Minute als root (systemd-Timer) – richtet auch den Absturz-Wächter ein
  setup_crashwatch
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

# ---------------------------------------------------------------- Absturz-Wächter (N8 Kit 2.0)
# Jeder Dienst des Projekts bekommt ein Drop-in /etc/systemd/system/<unit>.d/n8-crashwatch-<N8_ID>.conf (je Projekt eigenes, falls
# sich mehrere N8-Systeme einen Dienst wie nginx teilen) mit ExecStopPost=+… crash-hook:
# systemd ruft es nach JEDEM Ende des Dienstes als root auf und übergibt SERVICE_RESULT, EXIT_CODE und EXIT_STATUS. Geplante Enden
# (Stoppen/Neustart von Hand, Update, Keep-Alive, Herunterfahren) laufen als systemd-Auftrag und werden übergangen; alles andere –
# Absturz (Signal), Fehlercode, Watchdog (Prozess hing), Speicher voll (OOM), Zeitüberschreitung, unerwartetes Ende – wird
# festgehalten: $STATE_DIR/crashes.jsonl (eine Zeile je Befund) und $STATE_DIR/crash/<id>.log (Journal, Python-Stack aus
# crash/fault-<unit>.log, Hänger-Befund aus crash/last-<unit>.json, Coredump-Kurzinfo). Neu gestartet wird der Dienst von systemd selbst
# (Restart=, bei Diensten ohne Restart= setzt das Drop-in Restart=on-failure); bleibt er „failed“, startet ihn der Keep-Alive neu.
# Das Webinterface zeigt die Befunde unter System → 💥 Abstürze und nach der Anmeldung als Hinweisfenster (bis „gelesen“).
crash_units() {
  local -A seen=(); local u ent list=()
  if ((${#N8_CRASH_UNITS[@]})); then list=("${N8_CRASH_UNITS[@]}")
  else
    list=("$N8_MAIN_UNIT")
    for ent in "${N8_UNITS[@]}" "${N8_KA_CHECKS[@]}"; do list+=("${ent%%|*}"); done
  fi
  for u in "${list[@]}"; do
    [[ "$u" =~ ^[A-Za-z0-9@._-]+\.service$ ]] || continue
    [[ "$u" == "$UPD_SVC" || "$u" == "$KA_SVC" ]] && continue
    [[ -n "${seen[$u]:-}" ]] && continue; seen[$u]=1; echo "$u"
  done
}
crash_label() {   # Bezeichnung eines Dienstes (aus N8_UNITS oder den Keep-Alive-Prüfungen)
  local ent u l
  for ent in "${N8_UNITS[@]}"; do IFS='|' read -r u l _ <<<"$ent"; [[ "$u" == "$1" && -n "$l" ]] && { echo "$l"; return; }; done
  [[ "$1" == "$N8_MAIN_UNIT" ]] && { echo "$N8_NAME"; return; }
  for ent in "${N8_KA_CHECKS[@]}"; do IFS='|' read -r u _ _ l <<<"$ent"; [[ "$u" == "$1" && -n "$l" ]] && { echo "$l"; return; }; done
  echo "${1%.service}"
}
setup_crashwatch() {
  local u d rs sep="" js="" n=0
  for u in $(crash_units); do rm -f "/etc/systemd/system/$u.d/n8-crashwatch-$N8_ID.conf" "/etc/systemd/system/$u.d/n8-crashwatch.conf"; done
  systemctl daemon-reload >/dev/null 2>&1 || true
  for u in $(crash_units); do
    systemctl cat "$u" >/dev/null 2>&1 || continue
    d="/etc/systemd/system/$u.d"; install -d -o root -g root -m 755 "$d"
    rs="$(systemctl show -p Restart --value "$u" 2>/dev/null)"
    {
      echo "# $N8_NAME – Absturz-Wächter (von n8-admin.sh setup-crashwatch geschrieben, wird bei jedem Update erneuert)"
      echo "[Service]"
      echo "ExecStopPost=+$SELF crash-hook $u"
      [[ -z "$rs" || "$rs" == no ]] && { echo "Restart=on-failure"; echo "RestartSec=5"; rs=on-failure; }
    } > "$d/n8-crashwatch-$N8_ID.conf"
    chmod 644 "$d/n8-crashwatch-$N8_ID.conf"
    js+="$sep{\"unit\": \"$u\", \"label\": \"$(crash_label "$u" | sed 's/"/\x27/g')\", \"restart\": \"$rs\"}"; sep=", "; n=$((n + 1))
  done
  systemctl daemon-reload >/dev/null 2>&1 || true
  mkdir -p "$STATE_DIR/crash"
  printf '{"version": 1, "time": %s, "units": [%s]}\n' "$(date +%s)" "$js" > "$STATE_DIR/crashwatch.json"
  chmod 644 "$STATE_DIR/crashwatch.json"; chmod 750 "$STATE_DIR/crash"
  id "$SVC_USER" &>/dev/null && chown "$SVC_USER:$SVC_USER" "$STATE_DIR/crashwatch.json" "$STATE_DIR/crash"
  ok "Absturz-Wächter eingerichtet ($n Dienste: $(crash_units | tr '\n' ' '))"
}
# crash_record UNIT ART URSACHE QUELLE NEUGESTARTET [mit-Journal 0/1] – Befund schreiben (JSON sicher über python3)
crash_record() {
  local u="$1" ok_u=1
  [[ "$u" =~ ^[A-Za-z0-9@._-]+$ ]] || ok_u=0
  (( ok_u )) || return 0
  mkdir -p "$STATE_DIR/crash"
  N8C_DIR="$STATE_DIR" N8C_UNIT="$u" N8C_KIND="$2" N8C_REASON="$3" N8C_SOURCE="$4" N8C_RESTARTED="$5" N8C_JOURNAL="${6:-1}" \
  N8C_LABEL="$(crash_label "$u")" N8C_APP="$N8_NAME" N8C_RESULT="${SERVICE_RESULT:-}" N8C_CODE="${EXIT_CODE:-}" N8C_STATUS="${EXIT_STATUS:-}" \
  timeout 40 python3 - <<'PY' 2>&1 | logger -t "$N8_ID-crash" 2>/dev/null || true
import json, os, re, secrets, subprocess, time
E = os.environ
d, unit, kind = E["N8C_DIR"], E["N8C_UNIT"], E["N8C_KIND"]
cdir = os.path.join(d, "crash")
now = time.time()
cid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)

def read(p, n=200000):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()[-n:]
    except OSError:
        return ""

def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except Exception as e:  # noqa: BLE001
        return f"({cmd[0]}: {e})"

service, reason, extra = E.get("N8C_LABEL") or unit, E["N8C_REASON"], []
# Dateien der Anwendung je Dienst (crash/last-<unit>.json …), ältere Fassung ohne Dienstnamen als Rückfall
def own(name, ext):
    p = os.path.join(cdir, f"{name}-{unit}{ext}")
    return p if os.path.exists(p) else os.path.join(cdir, name + ext)
# Befund der Anwendung: Hänger der Event-Loop (crash/last-<unit>.json, höchstens 15 min alt)
f_last, f_fault, f_svcs = own("last", ".json"), own("fault", ".log"), own("services", ".json")
try:
    last = json.loads(read(f_last) or "null")
except ValueError:
    last = None
if isinstance(last, dict) and now - float(last.get("time") or 0) < 900:
    if last.get("service"):
        service = str(last["service"])[:120]
    reason += " – " + str(last.get("reason") or "")[:200]
    extra.append(f"=== Befund der Anwendung (crash/{os.path.basename(f_last)}) ===\n" + str(last.get("reason") or "") + "\n\n" + str(last.get("detail") or ""))
    try:
        os.remove(f_last)
    except OSError:
        pass
# faulthandler-Ausgabe (Python-Stack aller Threads beim harten Ende): nur der Teil seit dem letzten Start, falls er etwas enthält
fault = read(f_fault)
blk = fault.rsplit("\n=== ", 1)[-1] if fault else ""
if "Fatal Python error" in blk or "most recent call first" in blk:
    extra.append(f"=== Python-Stack beim Ende (crash/{os.path.basename(f_fault)}) ===\n" + blk[-60000:])
    m = re.search(r"Fatal Python error: ([^\n]+)", blk)
    if m and m.group(1) not in reason:
        reason += f" ({m.group(1).strip()[:120]})"
    # Zuordnung zum Teil der Anwendung: die Anwendung legt ihre Liste in crash/services.json ab
    try:
        svcs = [(re.compile(rx), lab) for rx, lab in json.loads(read(f_svcs) or "[]")]
    except (ValueError, re.error, TypeError):
        svcs = []
    cur = blk.split("Current thread", 1)[-1] if "Current thread" in blk else blk
    hits = []
    for f in re.findall(r'File "([^"]+)"', cur):            # faulthandler: innerste Stelle zuerst
        for rx, lab in svcs:
            if rx.search(f.replace("\\", "/")):
                if lab not in hits:
                    hits.append(lab)
                break
        if len(hits) == 2:
            break
    if hits and not (isinstance(last, dict) and last.get("service")):
        service = " ← ".join(hits)
    with open(f_fault, "a", encoding="utf-8") as f:
        f.write("\n=== (Befund " + cid + " festgehalten) ===\n")
if E.get("N8C_JOURNAL") == "1":
    j = run("journalctl", "-u", unit, "-n", "200", "--no-pager", "-o", "short-iso")
    extra.append("=== Journal des Dienstes (letzte 200 Zeilen) ===\n" + j)
    if E.get("N8C_RESULT") == "core-dump" and subprocess.run(["sh", "-c", "command -v coredumpctl"], capture_output=True).returncode == 0:
        extra.append("=== Coredump ===\n" + "\n".join(run("coredumpctl", "info", "-1", "--no-pager", "_SYSTEMD_UNIT=" + unit).splitlines()[:80]))
    if kind == "oom":
        extra.append("=== Kernel (OOM) ===\n" + "\n".join(run("journalctl", "-k", "-n", "60", "--no-pager", "-o", "short-iso").splitlines()))
head = [f"{E.get('N8C_APP') or 'N8'} – Befund {cid}", f"Zeit:     {time.strftime('%Y-%m-%d %H:%M:%S')}", f"Dienst:   {unit}",
        f"Teil:     {service}", f"Ursache:  {reason}", f"systemd:  Result={E.get('N8C_RESULT') or '-'} Exit={E.get('N8C_CODE') or '-'}/{E.get('N8C_STATUS') or '-'}",
        f"Neustart: {'ja (automatisch)' if E.get('N8C_RESTARTED') == '1' else 'nein'}", f"Quelle:   {E.get('N8C_SOURCE')}"]
os.makedirs(cdir, exist_ok=True)
with open(os.path.join(cdir, cid + ".log"), "w", encoding="utf-8") as f:
    f.write("\n".join(head) + "\n\n" + "\n\n".join(extra) + "\n")
entry = {"id": cid, "time": round(now, 3), "unit": unit, "app": E.get("N8C_APP", ""), "service": service, "kind": kind,
         "reason": reason[:400], "source": E.get("N8C_SOURCE", ""), "restarted": E.get("N8C_RESTARTED") == "1", "log": cid + ".log",
         "result": E.get("N8C_RESULT", ""), "exit": (E.get("N8C_CODE", "") + "/" + E.get("N8C_STATUS", "")).strip("/")}
fd = os.open(os.path.join(d, "crashes.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
os.write(fd, (json.dumps(entry, ensure_ascii=False) + "\n").encode())
os.close(fd)
print(f"💥 {unit}: {kind} – {service}: {reason} (crash/{cid}.log)")
PY
  crash_own
}
crash_own() {   # Befunde gehören dem Dienstbenutzer (das Webinterface markiert sie als gelesen), nur für ihn lesbar
  id "$SVC_USER" &>/dev/null || return 0
  chown -R "$SVC_USER:$SVC_USER" "$STATE_DIR/crash" 2>/dev/null; chown "$SVC_USER:$SVC_USER" "$STATE_DIR/crashes.jsonl" 2>/dev/null
  chmod 750 "$STATE_DIR/crash" 2>/dev/null; chmod 640 "$STATE_DIR/crashes.jsonl" "$STATE_DIR"/crash/*.log 2>/dev/null
  return 0
}
crash_hook() {   # crash_hook UNIT – systemd ExecStopPost=+ (als root), nach JEDEM Ende des Dienstes
  local -; set +e +o pipefail
  local u="$1" res="${SERVICE_RESULT:-}" code="${EXIT_CODE:-}" st="${EXIT_STATUS:-}" kind reason rs restarted=0
  [[ "$u" =~ ^[A-Za-z0-9@._-]+\.service$ ]] || return 0
  # geplantes Ende: für den Dienst läuft ein Auftrag (stop/restart von Hand, Update, Keep-Alive, Herunterfahren)
  if systemctl list-jobs --no-legend 2>/dev/null | awk '{print $2}' | grep -qxF "$u"; then return 0; fi
  local sig="$st"; [[ "$code" == killed || "$code" == dumped ]] && sig="SIG${st#SIG}"
  case "$res" in
    success)
      [[ "$code" == exited ]] && reason="hat sich selbst beendet (Exit $st)" || reason="wurde von außen beendet ($sig)"
      kind="exit" ;;
    watchdog) kind=watchdog; reason="systemd-Watchdog: keine Rückmeldung mehr – der Prozess hing und wurde beendet ($sig)" ;;
    oom-kill) kind=oom; reason="Speicher voll – der Kernel hat den Prozess beendet (OOM)" ;;
    core-dump|signal) kind=crash; reason="Absturz durch $sig$([[ $res == core-dump ]] && echo ', Coredump')" ;;
    exit-code) kind=crash; reason="mit Fehlercode $st beendet" ;;
    timeout) kind=timeout; reason="Zeitüberschreitung beim Starten/Stoppen" ;;
    start-limit-hit) kind=crash; reason="zu viele Neustarts hintereinander – systemd gibt auf (Keep-Alive startet ihn später neu)" ;;
    *) kind=crash; reason="beendet: ${res:-unbekannt} ($code $st)" ;;
  esac
  rs="$(systemctl show -p Restart --value "$u" 2>/dev/null)"
  case "$rs" in always) restarted=1 ;; on-failure|on-abnormal|on-abort|on-watchdog) [[ "$res" != success ]] && restarted=1 ;; esac
  [[ "$res" == start-limit-hit ]] && restarted=0
  crash_record "$u" "$kind" "$reason" systemd "$restarted" 1
  return 0
}
# Keep-Alive-Teil: Dienste im Zustand „failed“ wieder starten, Neustarts ohne Drop-in erkennen, Liste kurz halten
crash_keepalive() {   # crash_keepalive ZUSTANDSDATEI JETZT PAUSE
  local st="$1" now="$2" pause="$3" u n old res hour cnt miss=0
  # nach einem Update über eine ältere n8-admin.sh (die den Wächter noch nicht kannte) richtet ihn der Keep-Alive selbst ein
  for u in $(crash_units); do
    [[ -f "/etc/systemd/system/$u.d/n8-crashwatch-$N8_ID.conf" ]] && continue
    systemctl cat "$u" >/dev/null 2>&1 && miss=1
  done
  (( miss )) && { ka_log "🛡️ Absturz-Wächter fehlte – wird eingerichtet"; setup_crashwatch >/dev/null 2>&1; }
  for u in $(crash_units); do
    systemctl cat "$u" >/dev/null 2>&1 || continue
    [[ -f "$STATE_DIR/keepalive.hold/$u" ]] && continue
    n="$(systemctl show -p NRestarts --value "$u" 2>/dev/null)"; [[ "$n" =~ ^[0-9]+$ ]] || n=""
    old="$(ka_json "$st" "nrestarts:$u")"
    if [[ -n "$n" && -n "$old" ]] && (( n > old )) && [[ ! -f "/etc/systemd/system/$u.d/n8-crashwatch-$N8_ID.conf" ]]; then
      res="$(systemctl show -p Result --value "$u" 2>/dev/null)"
      crash_record "$u" restart "systemd hat den Dienst $((n - old))× neu gestartet (Result=${res:-?}; Absturz-Wächter fehlt – sudo $SELF setup-crashwatch)" keepalive 1 1
    fi
    [[ -n "$n" ]] && ka_json "$st" "nrestarts:$u" "$n" >/dev/null
    if [[ "$(systemctl is-active "$u" 2>/dev/null)" == failed ]] && systemctl is-enabled "$u" >/dev/null 2>&1 && (( now >= pause )); then
      hour=$(ka_json "$st" "hour:$u"); cnt=$(ka_json "$st" "count:$u"); cnt=${cnt:-0}
      [[ -z "$hour" || $(( now - hour )) -ge 3600 ]] && { hour=$now; cnt=0; ka_json "$st" "hour:$u" "$now" >/dev/null; }
      if (( cnt < N8_KA_MAX_HOUR )); then
        res="$(systemctl show -p Result --value "$u" 2>/dev/null)"
        ka_log "↻ $u war ausgefallen (failed, Result=${res:-?}) – Keep-Alive startet ihn neu"
        crash_record "$u" restart "Dienst war ausgefallen (failed, Result=${res:-?}) – Keep-Alive hat ihn neu gestartet" keepalive 1 1
        systemctl reset-failed "$u" >/dev/null 2>&1; systemctl restart "$u" >/dev/null 2>&1
        ka_json "$st" "count:$u" $((cnt + 1)) >/dev/null; ka_json "$st" "last:$u" "$now" >/dev/null
        old=$(ka_json "$st" "total:$u"); ka_json "$st" "total:$u" $(( ${old:-0} + 1 )) >/dev/null
      fi
    fi
  done
  crash_trim
}
crash_trim() {   # nur die letzten N8_CRASH_KEEP Befunde behalten, verwaiste Protokolle löschen
  local f="$STATE_DIR/crashes.jsonl"
  [[ -f "$f" ]] || return 0
  (( $(wc -l < "$f") > N8_CRASH_KEEP )) || return 0
  N8C_DIR="$STATE_DIR" N8C_KEEP="$N8_CRASH_KEEP" python3 - <<'PY' || true
import json, os
d = os.environ["N8C_DIR"]; keep = int(os.environ["N8C_KEEP"])
p = os.path.join(d, "crashes.jsonl")
lines = open(p, encoding="utf-8", errors="replace").read().splitlines()[-keep:]
ids = set()
for l in lines:
    try:
        ids.add(json.loads(l)["id"])
    except (ValueError, KeyError, TypeError):
        pass
with open(p + ".tmp", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
os.replace(p + ".tmp", p)
cd = os.path.join(d, "crash")
for n in os.listdir(cd) if os.path.isdir(cd) else []:
    if n.endswith(".log") and n[:-4] not in ids and not n.startswith("fault"):
        os.remove(os.path.join(cd, n))
PY
  crash_own
}
crash_show() {
  local f="$STATE_DIR/crashes.jsonl"
  [[ -s "$f" ]] || { ok "noch keine Abstürze festgehalten ($f)"; return 0; }
  python3 - "$f" <<'PY'
import json, sys, time
for l in open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()[-30:]:
    try:
        e = json.loads(l)
    except ValueError:
        continue
    print(f"{time.strftime('%d.%m. %H:%M:%S', time.localtime(e.get('time', 0)))}  {e.get('unit', ''):<28} {e.get('kind', ''):<10} "
          f"{e.get('service', '')}: {e.get('reason', '')}  [crash/{e.get('log', '')}]")
PY
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
  for u in $(crash_units); do
    systemctl cat "$u" >/dev/null 2>&1 || continue
    grep -qF "ExecStopPost=+$SELF crash-hook $u" "/etc/systemd/system/$u.d/n8-crashwatch-$N8_ID.conf" 2>/dev/null \
      && ck ok systemd "Absturz-Wächter für $u eingerichtet" || ck bad systemd "Absturz-Wächter für $u fehlt oder ist veraltet"
  done
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
  perm_bad_in systemd && { setup_units; setup_crashwatch; grep -q "NoNewPrivileges=yes" <<<"${CK[*]}" && web_unit_dropin; }
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
# ka_local URL – Weiterleitung (z. B. http → https, wenn die Anwendung HTTPS selbst macht) auf denselben Weg bei 127.0.0.1 umbiegen:
# so wird immer die Anwendung auf diesem Rechner gefragt, nie die öffentliche Adresse (Hairpin-NAT, Zertifikat, „nur lokal“).
ka_local() {
  local r="$1" proto rest hp port path
  proto="${r%%://*}"; rest="${r#*://}"; hp="${rest%%/*}"; path="/${rest#*/}"; [[ "$rest" == */* ]] || path="/"
  if [[ "$hp" =~ :([0-9]+)$ ]]; then port="${BASH_REMATCH[1]}"; elif [[ "$proto" == https ]]; then port=443; else port=80; fi
  [[ "$proto" == http || "$proto" == https ]] || return 1
  echo "$proto://127.0.0.1:$port$path"
}
# ka_get URL – Antwort holen (folgt höchstens zwei Weiterleitungen, jeweils zurück auf 127.0.0.1); setzt KA_CODE und KA_BODY
ka_get() {
  local url="$1" i out code red
  KA_CODE=000; KA_BODY=""
  for i in 1 2 3; do
    out="$(curl -sk -m 8 -w $'\n%{http_code} %{redirect_url}' "$url" 2>/dev/null || true)"
    code="$(tail -1 <<<"$out")"; red="${code#* }"; code="${code%% *}"
    KA_CODE="${code:-000}"; KA_BODY="$(sed '$d' <<<"$out")"
    [[ "$KA_CODE" =~ ^30[1278]$ && -n "$red" && "$red" != "$code" ]] || return 0
    url="$(ka_local "$red")" || return 0
  done
}
ka_http() { ka_get "$1"; [[ "$KA_CODE" =~ ^[1-4][0-9][0-9]$ && ! "$KA_CODE" =~ ^30 ]]; }   # jede Antwort außer 5xx und außer einer Weiterleitung ins Leere
declare -A KA_HEALTH=()
ka_health() {   # ka_health URL#punkt – /api/n8/health der Anwendung (nur von 127.0.0.1): {"items": {"punkt": {"ok": true, "why": "…"}}}
  # Rückgabe 0 = gesund, 1 = die Anwendung meldet den Punkt als gestört (→ Neustart), 2 = Zustand unbekannt (keine/fremde Antwort –
  # kein Neustart des Dienstes; ob die Weboberfläche selbst lebt, prüft ihre eigene http-Prüfung)
  local url="${1%%#*}" item="${1#*#}" body
  if [[ -z "${KA_HEALTH[$url]+x}" ]]; then
    ka_get "$url"
    if [[ "$KA_CODE" == 200 ]]; then KA_HEALTH[$url]="$KA_BODY"; else KA_HEALTH[$url]="{\"error\": \"Zustand unbekannt – /api/n8/health antwortet mit HTTP $KA_CODE\"}"; fi
  fi
  body="${KA_HEALTH[$url]}"
  python3 -c 'import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("Zustand unbekannt – /api/n8/health liefert kein JSON"); sys.exit(2)
if not isinstance(d, dict) or "items" not in d:
    print((d.get("error") if isinstance(d, dict) else "") or "Zustand unbekannt"); sys.exit(2)
i = d["items"].get(sys.argv[2])
if i is None:
    print("Zustand unbekannt – " + sys.argv[2] + " fehlt in /api/n8/health"); sys.exit(2)
if i.get("ok", True):
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
    # nur Zahlen zurückgeben: der Datenordner gehört dem Dienst – nichts davon darf in bash-Arithmetik etwas ausführen
    [[ -f "$f" ]] && while IFS= read -r line; do [[ "${line%%=*}" == "$k" ]] && { line="${line#*=}"; [[ "$line" =~ ^[0-9]{1,12}$ ]] && echo "$line"; return 0; }; done < "$f"
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
        health) why="$(ka_health "$tgt" 2>&1)"; case $? in 0) why="" ;; 2) healthy=3 ;; *) healthy=0 ;; esac ;;
        fn)   why="$("$tgt" 2>&1)"; [[ $? == 0 ]] && why="" || { healthy=0; why="$(tail -1 <<<"$why")"; why="${why:-Prüfung $tgt fehlgeschlagen}"; } ;;
      esac
      # eine Verbindung nach draußen kann ohne Internet nicht stehen – dann nicht neu starten, nur melden
      if (( ! healthy && ! net )) && [[ " ${N8_KA_NET_UNITS[*]} " == *" $u "* ]]; then why="$why (Internet weg – kein Neustart)"; healthy=2; fi
    fi
    fails=$(ka_json "$st" "fails:$ck"); fails=${fails:-0}
    if (( healthy == 3 )); then   # Zustand unbekannt: melden, aber nie deswegen neu starten
      [[ "$(ka_json "$st" "unknown:$ck")" == 1 ]] || { ka_log "? $u: ${why//\"/\'}"; ka_json "$st" "unknown:$ck" 1 >/dev/null; }
      ka_json "$st" "fails:$ck" 0 >/dev/null
      rows+="$sep{\"unit\": \"$u\", \"label\": \"${label:-$u}\", \"state\": \"unknown\", \"active\": \"$act\", \"why\": \"${why//\"/\'}\", \"fails\": 0}"
    elif (( healthy == 1 )); then
      ka_json "$st" "unknown:$ck" 0 >/dev/null
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
          ka_log "↻ $u neu gestartet ($why, seit $fails min)"
          crash_record "$u" keepalive "Keep-Alive: ${label:-$u} – $why (seit $fails min) – neu gestartet" keepalive 1 1
          [[ "$act" == failed ]] && systemctl reset-failed "$u" >/dev/null 2>&1
          systemctl restart "$u" >/dev/null 2>&1
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
  # --- Absturz-Wächter: ausgefallene Dienste neu starten, Neustarts ohne Drop-in erkennen
  crash_keepalive "$st" "$now" "$pause"
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
  id "$SVC_USER" &>/dev/null && chown "$SVC_USER:$SVC_USER" "$STATE_DIR/keepalive.log" "$STATE_DIR/keepalive.json" "$st" 2>/dev/null
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
  setup-crashwatch) setup_crashwatch ;;
  crash-hook) crash_hook "${2:-}" ;;
  crashes) crash_show ;;
  update) do_update "${2:-}" ;;
  *) echo "Aufruf: $SELF check-perms [--json] | fix-perms | sudo-setup | setup-units | setup-keepalive | keepalive | setup-crashwatch | crash-hook UNIT | crashes | update [--auto]"; exit 2 ;;
esac
