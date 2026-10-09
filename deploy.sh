#!/bin/sh
# Vom PC aus auf ein Phone kopieren und dort installieren: ./deploy.sh furios@phone.local
set -e
TARGET="${1:?Ziel angeben, z. B. furios@phone.local}"
cd "$(dirname "$0")"
tar --exclude=__pycache__ -czf - keyfinder bin data install.sh |
    ssh "$TARGET" 'set -e; d=$(mktemp -d); tar -xzf - -C "$d"; sh "$d/install.sh"; rm -rf "$d"'
