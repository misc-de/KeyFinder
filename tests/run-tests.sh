#!/bin/sh
# Alle Tests auf einem privaten Session-Bus mit Fake-BlueZ; echtes Bluetooth
# und die echte Konfiguration bleiben unberührt.
set -e
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export KEYFINDER_BUS=session
export KEYFINDER_CONFIG="$TMP/tags.json"
export XDG_CONFIG_HOME="$TMP/config"
export KEYFINDER_DATA="$TMP/data"
export PYTHONWARNINGS=ignore::DeprecationWarning
# Nie echtes systemctl: die App schaltet sonst den Dienst auf diesem Rechner.
export KEYFINDER_SYSTEMCTL="$PWD/tests/fake-bin/systemctl"
export FAKE_SYSTEMCTL_LOG="$TMP/systemctl.log"
dbus-run-session -- python3 -m unittest discover -s tests -v "$@"
