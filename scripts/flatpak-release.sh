#!/usr/bin/env bash
# Flatpak bauen (x86_64 + aarch64), signieren und für GitHub Pages bereitlegen.
#
#   scripts/flatpak-release.sh            # bauen, signieren, gh-pages lokal committen
#   scripts/flatpak-release.sh --push     # zusätzlich gh-pages pushen
#   NO_BUILD=1 scripts/flatpak-release.sh # nur signieren und veröffentlichen
#
# aarch64 wird über qemu-user (binfmt) gebaut und braucht dafür
# org.gnome.Sdk//50 für aarch64. Der Signierschlüssel liegt in einem eigenen
# GnuPG-Verzeichnis, nicht im persönlichen Schlüsselbund.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APPID=io.github.miscde.KeyFinder
MANIFEST=$APPID.yaml
REPO=repo
GPGHOME="${GPGHOME:-$HOME/.local/share/keyfinder-flatpak}"
KEY=$(gpg --homedir "$GPGHOME" --list-keys --with-colons | awk -F: '/^fpr/{print $10; exit}')
[[ -n "$KEY" ]] || { echo "Kein Schlüssel in $GPGHOME" >&2; exit 1; }
GPGARGS=(--gpg-sign="$KEY" --gpg-homedir="$GPGHOME")

if [[ -z "${NO_BUILD:-}" ]]; then
    for arch in x86_64 aarch64; do
        echo "==> Baue $arch"
        flatpak-builder --force-clean --disable-updates --repo="$REPO" --arch="$arch" \
            ".flatpak-build/$arch" "$MANIFEST"
    done
fi

# Jeden Ref signieren: App und Zusatzpakete (.Locale, .Debug), alle Architekturen.
# build-sign signiert sonst nur die App der eigenen Architektur, und Flatpak
# warnt beim Installieren über "no signatures found".
for ref in $(ostree --repo="$REPO" refs | grep -E '^(app|runtime)/'); do
    IFS=/ read -r kind id arch branch <<< "$ref"
    echo "==> Signiere $ref"
    flatpak build-sign "$REPO" "$id" "$branch" --arch="$arch" \
        $([[ $kind == runtime ]] && echo --runtime) "${GPGARGS[@]}"
done
# Alte Deltas tragen evtl. unsignierte Commits in sich.
rm -rf "$REPO/deltas" "$REPO/delta-indexes"
flatpak build-update-repo --generate-static-deltas --prune "${GPGARGS[@]}" "$REPO"

scripts/publish-pages.sh "$@"
