#!/usr/bin/env bash
# Build the Flatpak (x86_64 + aarch64), sign it and prepare it for GitHub Pages.
#
#   scripts/flatpak-release.sh            # build, sign, commit gh-pages locally
#   scripts/flatpak-release.sh --push     # and push gh-pages
#   NO_BUILD=1 scripts/flatpak-release.sh # only sign and publish
#
# aarch64 is built through qemu-user (binfmt) and needs org.gnome.Sdk//50 for
# aarch64. The signing key lives in its own GnuPG directory, not in the
# personal keyring.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APPID=io.github.miscde.KeyFinder
MANIFEST=$APPID.yaml
REPO=repo
GPGHOME="${GPGHOME:-$HOME/.local/share/keyfinder-flatpak}"
KEY=$(gpg --homedir "$GPGHOME" --list-keys --with-colons | awk -F: '/^fpr/{print $10; exit}')
[[ -n "$KEY" ]] || { echo "No key in $GPGHOME" >&2; exit 1; }
GPGARGS=(--gpg-sign="$KEY" --gpg-homedir="$GPGHOME")

if [[ -z "${NO_BUILD:-}" ]]; then
    for arch in x86_64 aarch64; do
        echo "==> Building $arch"
        flatpak-builder --force-clean --disable-updates --repo="$REPO" --arch="$arch" \
            ".flatpak-build/$arch" "$MANIFEST"
    done
fi

# Sign every ref: the app and its extras (.Locale, .Debug), all architectures.
# build-sign alone signs only the app of the own architecture, and Flatpak
# then warns "no signatures found" on install.
for ref in $(ostree --repo="$REPO" refs | grep -E '^(app|runtime)/'); do
    IFS=/ read -r kind id arch branch <<< "$ref"
    echo "==> Signing $ref"
    flatpak build-sign "$REPO" "$id" "$branch" --arch="$arch" \
        $([[ $kind == runtime ]] && echo --runtime) "${GPGARGS[@]}"
done
# Old deltas may carry unsigned commits.
rm -rf "$REPO/deltas" "$REPO/delta-indexes"
flatpak build-update-repo --generate-static-deltas --prune "${GPGARGS[@]}" "$REPO"

scripts/publish-pages.sh "$@"
