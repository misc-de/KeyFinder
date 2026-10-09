#!/bin/sh
# Copy to a phone from the PC and install there: ./deploy.sh furios@phone.local
set -e
TARGET="${1:?give a target, e.g. furios@phone.local}"
cd "$(dirname "$0")"
tar --exclude=__pycache__ -czf - keyfinder bin data install.sh VERSION |
    ssh "$TARGET" 'set -e; d=$(mktemp -d); tar -xzf - -C "$d"; sh "$d/install.sh"; rm -rf "$d"'
