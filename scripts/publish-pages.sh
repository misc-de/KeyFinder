#!/usr/bin/env bash
# Puts the Flatpak repo, .flatpakref/.flatpakrepo and a short start page into
# the gh-pages branch (one commit, no history – the repo is a cache).
#   scripts/publish-pages.sh [--push]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APPID=io.github.miscde.KeyFinder
REPO=repo
branch=gh-pages
worktree="$(mktemp -d)"
trap 'git worktree remove --force "$worktree" 2>/dev/null || true; rm -rf "$worktree"' EXIT

[[ -d "$REPO/objects" ]] || { echo "No OSTree repo in $REPO/" >&2; exit 1; }
echo "Publishing:"
find "$REPO/refs/heads/app" -type f | sed "s|$REPO/refs/heads/|  |"

git worktree add --force --detach "$worktree" >/dev/null
git -C "$worktree" checkout -q --orphan "$branch.new"
git -C "$worktree" rm -rq --cached . 2>/dev/null || true
find "$worktree" -mindepth 1 -maxdepth 1 -not -name .git -exec rm -rf {} +

touch "$worktree/.nojekyll"                     # Jekyll would swallow underscore folders
cp data/$APPID.flatpakref data/$APPID.flatpakrepo data/$APPID.gpg "$worktree/"
cp data/icons/128x128/$APPID.png "$worktree/icon.png"
cp -r "$REPO" "$worktree/repo"

cat > "$worktree/index.html" <<'HTML'
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Key Finder – Flatpak</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.5}
pre{background:#8882;border-radius:6px;padding:1rem;overflow:auto}img{vertical-align:middle}</style>
</head><body>
<h1><img src="icon.png" width="64" alt=""> Key Finder</h1>
<p>Find Bluetooth key tags (iTag): beep, signal strength, last place seen on a map.
Flatpak for <b>x86_64</b> and <b>aarch64</b>, signed.</p>
<pre>flatpak install --user https://misc-de.github.io/KeyFinder/io.github.miscde.KeyFinder.flatpakref</pre>
<p>Updates: <code>flatpak update</code> · Source:
<a href="https://github.com/misc-de/KeyFinder">github.com/misc-de/KeyFinder</a></p>
</body></html>
HTML

git -C "$worktree" add -A
git -C "$worktree" commit -q -m "Flatpak-Repo $(cat VERSION)"
git branch -f "$branch" "$(git -C "$worktree" rev-parse HEAD)"
git -C "$worktree" checkout -q --detach
git branch -D "$branch.new" >/dev/null
echo "gh-pages committed."
if [[ "${1:-}" == "--push" ]]; then
    git push -f origin "$branch"
else
    echo "Not pushed yet:  git push -f origin $branch"
fi
