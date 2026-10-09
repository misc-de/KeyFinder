#!/bin/sh
# Entfernt eine mit install.sh angelegte Installation (Einstellungen bleiben).
PREFIX="${PREFIX:-$HOME/.local}"
SYSTEMCTL="${KEYFINDER_SYSTEMCTL:-systemctl}"
"$SYSTEMCTL" --user disable --now keyfinder-tracker.service 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/keyfinder-tracker.service"
"$SYSTEMCTL" --user daemon-reload 2>/dev/null || true
rm -rf "$PREFIX/lib/keyfinder" "$PREFIX/bin/keyfinder" \
       "$PREFIX/share/applications/io.github.miscde.KeyFinder.desktop"
find "$PREFIX/share/icons/hicolor" -name "io.github.miscde.KeyFinder.png" -delete 2>/dev/null
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
echo "Key Finder entfernt. Tags und Orte liegen weiter in ~/.config/keyfinder und ~/.local/share/keyfinder."
