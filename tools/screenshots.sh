#!/bin/sh
# Recreate the README pictures: invisible (GTK Broadway, headless Chromium as
# display client), fake BlueZ, invented tags, English UI. Nothing on this
# machine is switched: systemctl is a stand-in, the configuration is temporary.
#   tools/screenshots.sh            → data/screenshots/*.png
set -e
cd "$(dirname "$0")/.."
if [ -z "$KF_INNER" ]; then
    KF_INNER=1 exec dbus-run-session -- "$0" "$@"
fi
WORK=$(mktemp -d)
gtk4-broadwayd :7 >/dev/null 2>&1 &
B=$!
chromium --headless=new --disable-gpu --no-first-run --user-data-dir="$WORK/chrome" \
         --window-size=800,800 http://127.0.0.1:8087/ >/dev/null 2>&1 &
C=$!
cleanup() { kill $C $B 2>/dev/null; pkill -f "user-data-dir=$WORK/chrome" 2>/dev/null; rm -rf "$WORK"; true; }
trap cleanup EXIT
sleep 2
export GDK_BACKEND=broadway BROADWAY_DISPLAY=:7 KEYFINDER_BUS=session \
       KEYFINDER_CONFIG="$WORK/config/tags.json" KEYFINDER_DATA="$WORK/data" \
       KEYFINDER_SYSTEMCTL="$PWD/tests/fake-bin/systemctl" PYTHONWARNINGS=ignore \
       ADW_DEBUG_COLOR_SCHEME=prefer-dark LANGUAGE=en
mkdir -p data/screenshots
python3 tools/screenshots.py data/screenshots "$WORK"
echo "Pictures in data/screenshots/"
