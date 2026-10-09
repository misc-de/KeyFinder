#!/bin/sh
# Installs Key Finder for the current user into ~/.local (no sudo).
set -e
cd "$(dirname "$0")"
PREFIX="${PREFIX:-$HOME/.local}"
rm -rf "$PREFIX/lib/keyfinder"
mkdir -p "$PREFIX/lib/keyfinder" "$PREFIX/bin" "$PREFIX/share/applications"
cp -r keyfinder "$PREFIX/lib/keyfinder/"
rm -rf "$PREFIX/lib/keyfinder/keyfinder/__pycache__"
cp VERSION "$PREFIX/lib/keyfinder/VERSION"
ln -sf "$PREFIX/lib/keyfinder/keyfinder-launcher" "$PREFIX/bin/keyfinder"
cp bin/keyfinder "$PREFIX/lib/keyfinder/keyfinder-launcher"
# Icon before the desktop file: Phosh reads new entries right away and would
# otherwise keep the fallback icon. The desktop file is created anew (not
# overwritten) so that Phosh looks again on a reinstall too.
for dir in data/icons/*/; do
    size=$(basename "$dir")
    mkdir -p "$PREFIX/share/icons/hicolor/$size/apps"
    cp "$dir/io.github.miscde.KeyFinder.png" "$PREFIX/share/icons/hicolor/$size/apps/"
done
# old SVG icon of earlier versions, GTK would prefer it
rm -f "$PREFIX/share/icons/hicolor/scalable/apps/io.github.miscde.KeyFinder.svg"
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
DESKTOP="$PREFIX/share/applications/io.github.miscde.KeyFinder.desktop"
sed "s|^Exec=keyfinder|Exec=$PREFIX/bin/keyfinder|" data/io.github.miscde.KeyFinder.desktop > "$DESKTOP.tmp"
if [ -e "$DESKTOP" ]; then rm -f "$DESKTOP"; sleep 1; fi
mv "$DESKTOP.tmp" "$DESKTOP"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true

# Background service: only put the unit file in place. Whether it runs,
# --sync-service derives from the saved tags (this also repairs after updates).
SYSTEMCTL="${KEYFINDER_SYSTEMCTL:-systemctl}"
UNITDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNITDIR"
sed "s|%h/.local/bin/keyfinder|$PREFIX/bin/keyfinder|" data/keyfinder-tracker.service \
    > "$UNITDIR/keyfinder-tracker.service"
"$SYSTEMCTL" --user daemon-reload 2>/dev/null || true
KEYFINDER_SYSTEMCTL="$SYSTEMCTL" "$PREFIX/bin/keyfinder" --sync-service --restart || true
echo "Key Finder installed: $PREFIX/bin/keyfinder"
