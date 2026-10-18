#!/usr/bin/env bash
# Publish once; never overwrite or change an existing repository.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
OWNER="srkftw"
NAME="lemma"
FULL="$OWNER/$NAME"
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
for tool in git python3 gh; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required tool is missing: $tool. Install it on your own development machine before publishing."
done
python3 "$ROOT/scripts/check_scaffold.py" --root "$ROOT"
gh auth status --hostname github.com >/dev/null 2>&1 || fail "Authenticate first with: gh auth login --hostname github.com"
LOGIN="$(gh api --hostname github.com user --jq .login)"
[[ "$LOGIN" == "$OWNER" ]] || fail "Authenticated as '$LOGIN', expected '$OWNER'; no repository was created."
if gh repo view "github.com/$FULL" --json nameWithOwner >/dev/null 2>&1; then
  fail "A repository already exists or is accessible at $FULL. Refusing to reuse or overwrite it."
fi
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TOP="$(git -C "$ROOT" rev-parse --show-toplevel)"
  [[ "$(cd "$TOP" && pwd -P)" == "$ROOT" ]] || fail "The scaffold is inside a different repository; extract it to a separate directory."
  [[ "$(git -C "$ROOT" branch --show-current)" == "main" ]] || fail "Expected a local main branch; refusing to change branches."
  [[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || fail "Worktree is not clean. Review and commit changes before publishing."
  git -C "$ROOT" rev-parse --verify HEAD >/dev/null 2>&1 || fail "The repository has no commit. Create and review the initial commit first."
else
  git -C "$ROOT" init --initial-branch=main
  if ! git -C "$ROOT" var GIT_AUTHOR_IDENT >/dev/null 2>&1; then
    git -C "$ROOT" config user.name "$OWNER"
    git -C "$ROOT" config user.email "100889427+srkftw@users.noreply.github.com"
  fi
  git -C "$ROOT" add --all
  git -C "$ROOT" commit -m "Initialize Lemma architecture, construction plan and first Codex task"
fi
if git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
  fail "An origin remote is already configured. Refusing to change it or push automatically."
fi
DESC="$(python3 - "$ROOT/repository.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    print(json.load(f)['description'])
PY
)"
GH_HOST=github.com gh repo create "$FULL" --private --source="$ROOT" --remote=origin --push --description="$DESC"
CHECK="$(gh repo view "github.com/$FULL" --json nameWithOwner,isPrivate --jq '[.nameWithOwner, (.isPrivate | tostring)] | @tsv')"
[[ "$CHECK" == "$FULL"$'\ttrue' ]] || fail "Publication returned, but expected private visibility was not verified. Inspect the GitHub repository before any further action."
printf '\nPublished private repository: https://github.com/%s\n' "$FULL"
printf 'Next assignment: codex/prompts/001-core0-freestanding-slice.html\n'
