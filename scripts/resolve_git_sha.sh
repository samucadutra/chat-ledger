#!/bin/sh
# Resolve the build's git SHA (used by the `git-sha` Docker build stage).
#
#   resolve_git_sha.sh [GITDIR]
#
# Order: a valid 40-hex $GIT_SHA override, then `git rev-parse HEAD` (when git
# is installed), then a plain read of GITDIR/HEAD (+ refs / packed-refs), else
# "unknown". Prints exactly one line.
set -eu
gitdir="${1:-.git}"

is_sha() { printf '%s' "$1" | grep -Eq '^[0-9a-f]{40}$'; }

override="$(printf '%s' "${GIT_SHA:-}" | tr 'A-F' 'a-f' | tr -d '[:space:]')"
if is_sha "$override"; then echo "$override"; exit 0; fi

sha=""
if command -v git >/dev/null 2>&1 && [ -e "$gitdir" ]; then
  sha="$(git --git-dir="$gitdir" rev-parse HEAD 2>/dev/null || true)"
fi
if ! is_sha "$sha" && [ -f "$gitdir/HEAD" ]; then
  head="$(tr -d '[:space:]' < "$gitdir/HEAD")"
  case "$head" in
    ref:*)
      ref="${head#ref:}"
      if [ -f "$gitdir/$ref" ]; then
        sha="$(tr -d '[:space:]' < "$gitdir/$ref")"
      elif [ -f "$gitdir/packed-refs" ]; then
        sha="$(grep " $ref\$" "$gitdir/packed-refs" | cut -d' ' -f1 | head -n1)"
      fi
      ;;
    *) sha="$head" ;;
  esac
fi
if is_sha "$sha"; then echo "$sha"; else echo "unknown"; fi
