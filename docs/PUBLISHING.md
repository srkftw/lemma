<!--
# GitHub publication and Codex handoff

## Current repository

`srkftw/lemma` is the owner's private GitHub repository. The connected repository
read confirmed its name, private visibility, default branch `main`, and push access.
The repository was initially empty; the starter is being committed through the
connected GitHub file/tree/commit APIs, without force-pushing or changing visibility.

This publishes source and instructions, not an implemented Core0 compiler or a
running Codex task. Select the repository and `main` in Codex, then assign
`codex/prompts/001-core0-freestanding-slice.md`. Codex should use a task branch and
return a reviewable change. Its own GitHub connection must have repository access;
publication alone does not configure a Codex environment or grant that connection access.

## Historical preparation

The starter was first prepared locally because the connection did not expose a
repository-creation action and the runtime had no authenticated GitHub CLI. The
owner subsequently created the repository. No credentials were requested in chat.

The ZIP and Git bundle supplied earlier are preparation snapshots. GitHub `main`
is the canonical published starter; its publication notes and metadata supersede
the preparation snapshots' statements that no remote exists.

## Retained bootstrap helper

`scripts/publish-github.sh` and its mocked tests remain as auditable host-only tooling.
The helper was designed to create a new private `srkftw/lemma` from a clean local
source tree using an authenticated GitHub CLI. It refuses existing repositories,
existing origins, dirty worktrees, the wrong account, and failed visibility checks.

**Do not run the helper for this existing repository.** Use ordinary branches and
reviewable commits instead. Do not delete the repository to make the helper run.
Its tests create temporary mock repositories and make no live GitHub requests.

No project license has been selected. Do not change visibility, add a license,
commit secrets/NDA material, or alter GitHub access controls as part of task 001.

-->
