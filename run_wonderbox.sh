#!/bin/bash
# Starts the WonderBox app and keeps it running.
#
# - Started at login (tools/install_autostart.sh) and by the desktop icon.
# - If the app crashes, it is started again after a short pause.
# - If the app is closed on purpose (ESC), it stays closed, so the desktop is
#   free for things like joining a new Wi-Fi network. The desktop icon starts
#   it again.
# - Only one copy runs at a time; a second start does nothing.
# Logs go to logs/app.log.

cd "$(dirname "$0")" || exit 1
export DISPLAY="${DISPLAY:-:0}"
mkdir -p logs

exec 9>"${WONDERBOX_LOCK:-/tmp/wonderbox.lock}"
if ! flock -n 9; then
    echo "=== $(date) already running; not starting a second copy ===" >> logs/app.log
    exit 0
fi

RESTART_PAUSE="${WONDERBOX_RESTART_PAUSE:-3}"
crashes=0
window_start=$(date +%s)

while true; do
    echo "=== start $(date) ===" >> logs/app.log
    ./venv/bin/python main.py >> logs/app.log 2>&1
    code=$?

    if [ "$code" -eq 0 ]; then
        echo "=== closed on purpose $(date); not restarting ===" >> logs/app.log
        exit 0
    fi

    # Crash: restart, but slow down if it keeps crashing (5 within a minute)
    now=$(date +%s)
    if [ $((now - window_start)) -gt 60 ]; then
        crashes=0
        window_start=$now
    fi
    crashes=$((crashes + 1))
    pause=$RESTART_PAUSE
    if [ "$crashes" -ge 5 ]; then
        pause=30
    fi
    echo "=== crashed (exit code $code) $(date); restarting in ${pause}s ===" >> logs/app.log
    sleep "$pause"
done
