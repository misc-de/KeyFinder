#!/bin/sh
# Installiert den Key Finder für den aktuellen Benutzer nach ~/.local (ohne sudo).
set -e
cd "$(dirname "$0")"
PREFIX="${PREFIX:-$HOME/.local}"
rm -rf "$PREFIX/lib/keyfinder"
mkdir -p "$PREFIX/lib/keyfinder" "$PREFIX/bin" "$PREFIX/share/applications"
cp -r keyfinder "$PREFIX/lib/keyfinder/"
rm -rf "$PREFIX/lib/keyfinder/keyfinder/__pycache__"
ln -sf "$PREFIX/lib/keyfinder/keyfinder-launcher" "$PREFIX/bin/keyfinder"
cp bin/keyfinder "$PREFIX/lib/keyfinder/keyfinder-launcher"
# Icon vor der Desktop-Datei: Phosh liest neue Einträge sofort und merkt sich
# sonst das Ersatzsymbol. Die Desktop-Datei wird neu angelegt (nicht
# überschrieben), damit Phosh auch bei einer Neuinstallation neu nachsieht.
for dir in data/icons/*/; do
    size=$(basename "$dir")
    mkdir -p "$PREFIX/share/icons/hicolor/$size/apps"
    cp "$dir/io.github.miscde.KeyFinder.png" "$PREFIX/share/icons/hicolor/$size/apps/"
done
# altes SVG-Icon früherer Versionen, GTK würde es sonst vorziehen
rm -f "$PREFIX/share/icons/hicolor/scalable/apps/io.github.miscde.KeyFinder.svg"
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
DESKTOP="$PREFIX/share/applications/io.github.miscde.KeyFinder.desktop"
sed "s|^Exec=keyfinder|Exec=$PREFIX/bin/keyfinder|" data/io.github.miscde.KeyFinder.desktop > "$DESKTOP.tmp"
if [ -e "$DESKTOP" ]; then rm -f "$DESKTOP"; sleep 1; fi
mv "$DESKTOP.tmp" "$DESKTOP"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true

# Hintergrunddienst: nur die Unit-Datei ablegen. Ob er läuft, leitet
# --sync-service aus den gespeicherten Tags ab (repariert auch nach Updates).
SYSTEMCTL="${KEYFINDER_SYSTEMCTL:-systemctl}"
UNITDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNITDIR"
sed "s|%h/.local/bin/keyfinder|$PREFIX/bin/keyfinder|" data/keyfinder-tracker.service \
    > "$UNITDIR/keyfinder-tracker.service"
"$SYSTEMCTL" --user daemon-reload 2>/dev/null || true
KEYFINDER_SYSTEMCTL="$SYSTEMCTL" "$PREFIX/bin/keyfinder" --sync-service --restart || true
echo "Key Finder installiert: $PREFIX/bin/keyfinder"
