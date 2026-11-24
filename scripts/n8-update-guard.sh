#!/bin/sh
# N8 update guard 1.0 – shared by the N8schicht services (same file in every repository).
# Runs as ExecStartPre=-/bin/sh <repo>/scripts/n8-update-guard.sh <repo> <state_dir>
# After an update from the web interface (file <state_dir>/update.pending) it counts the starts.
# The new code removes the file as soon as its web interface answers. After three starts without
# that, the checkout is reset to the previous commit and the outcome is written to update.result.
REPO="$1"; STATE="$2"; MAX="${3:-3}"
P="$STATE/update.pending"
[ -n "$REPO" ] && [ -n "$STATE" ] && [ -f "$P" ] || exit 0
get() { sed -n "s/^$1=//p" "$P" | head -n 1; }
OLD=$(get old); NEW=$(get new); TRIES=$(get tries); OV=$(get old_version); NV=$(get new_version)
TRIES=$(( ${TRIES:-0} + 1 ))
if [ "$TRIES" -le "$MAX" ]; then
    sed "s/^tries=.*/tries=$TRIES/" "$P" > "$P.tmp" && mv -f "$P.tmp" "$P"
    echo "n8-update-guard: start $TRIES of $MAX after the update ${OV:-$OLD} -> ${NV:-$NEW}"
    exit 0
fi
echo "n8-update-guard: the web interface did not come up after $MAX starts – rolling back to ${OV:-$OLD}"
MSG="rolled back to ${OV:-$OLD}"
if [ -n "$OLD" ] && git -C "$REPO" cat-file -e "$OLD^{commit}" 2>/dev/null; then
    git -C "$REPO" reset -q --hard "$OLD" || MSG="rollback failed (git reset)"
else
    MSG="rollback impossible: commit ${OLD:-?} unknown"
fi
NOW=$(date +%s)
printf '{"ok": false, "from": "%s", "to": "%s", "old": "%s", "new": "%s", "time": %s, "message": "%s"}\n' \
    "${OV:-$OLD}" "${NV:-$NEW}" "$OLD" "$NEW" "$NOW" "$MSG" > "$STATE/update.result"
rm -f "$P"
exit 0
