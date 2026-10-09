#!/bin/sh
# All tests on a private session bus with fake BlueZ and GeoClue; real
# Bluetooth and the real configuration stay untouched.
set -e
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export KEYFINDER_BUS=session
export KEYFINDER_CONFIG="$TMP/tags.json"
export XDG_CONFIG_HOME="$TMP/config"
export KEYFINDER_DATA="$TMP/data"
export PYTHONWARNINGS=ignore::DeprecationWarning
export LANGUAGE=en LC_ALL=C.UTF-8
# Never the real systemctl: the app would switch the service on this machine.
export KEYFINDER_SYSTEMCTL="$PWD/tests/fake-bin/systemctl"
export FAKE_SYSTEMCTL_LOG="$TMP/systemctl.log"
dbus-run-session -- python3 -m unittest discover -s tests -v "$@"
