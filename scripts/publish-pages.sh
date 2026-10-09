#!/usr/bin/env bash
# Legt Flatpak-Repo, .flatpakref/.flatpakrepo und eine kurze Startseite in den
# gh-pages-Branch (ein Commit, keine Historie – das Repo ist ein Cache).
#   scripts/publish-pages.sh [--push]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APPID=io.github.miscde.KeyFinder
REPO=repo
branch=gh-pages
worktree="$(mktemp -d)"
trap 'git worktree remove --force "$worktree" 2>/dev/null || true; rm -rf "$worktree"' EXIT

[[ -d "$REPO/objects" ]] || { echo "Kein OSTree-Repo in $REPO/" >&2; exit 1; }
echo "Wird veröffentlicht:"
find "$REPO/refs/heads/app" -type f | sed "s|$REPO/refs/heads/|  |"

git worktree add --force --detach "$worktree" >/dev/null
git -C "$worktree" checkout -q --orphan "$branch.new"
git -C "$worktree" rm -rq --cached . 2>/dev/null || true
find "$worktree" -mindepth 1 -maxdepth 1 -not -name .git -exec rm -rf {} +

touch "$worktree/.nojekyll"                     # Jekyll würde Unterstrich-Ordner verschlucken
cp data/$APPID.flatpakref data/$APPID.flatpakrepo data/$APPID.gpg "$worktree/"
cp data/icons/128x128/$APPID.png "$worktree/icon.png"
cp -r "$REPO" "$worktree/repo"

cat > "$worktree/index.html" <<'HTML'
<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Key Finder – Flatpak</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.5}
pre{background:#8882;border-radius:6px;padding:1rem;overflow:auto}img{vertical-align:middle}</style>
</head><body>
<h1><img src="icon.png" width="64" alt=""> Key Finder</h1>
<p>Bluetooth-Tags (iTag) finden: piepen lassen, Signalstärke, letzter Ort auf der Karte.
Flatpak für <b>x86_64</b> und <b>aarch64</b>, signiert.</p>
<pre>flatpak install --user https://misc-de.github.io/KeyFinder/io.github.miscde.KeyFinder.flatpakref</pre>
<p>Updates: <code>flatpak update</code> · Quellcode:
<a href="https://github.com/misc-de/KeyFinder">github.com/misc-de/KeyFinder</a></p>
</body></html>
HTML

git -C "$worktree" add -A
git -C "$worktree" commit -q -m "Flatpak-Repo $(cat VERSION)"
git branch -f "$branch" "$(git -C "$worktree" rev-parse HEAD)"
git -C "$worktree" checkout -q --detach
git branch -D "$branch.new" >/dev/null
echo "gh-pages committet."
if [[ "${1:-}" == "--push" ]]; then
    git push -f origin "$branch"
else
    echo "Noch nicht gepusht:  git push -f origin $branch"
fi
