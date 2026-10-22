#!/usr/bin/env bash
# Decides which revision of the jtm repository the workflows build jtm-index from.
#
# The ref is the first word of the JTM_REF file, unless OVERRIDE is set (the update workflow
# lets a person try another ref; the publish workflow never sets it). With REQUIRE_PINNED=true
# the ref must be a full 40-character commit SHA, because the publish job runs the code it
# builds with the signing key in its environment: a branch or tag that moves must not be able
# to change what that code is.
#
# Writes `ref=<ref>` and `pinned=<true|false>` to $GITHUB_OUTPUT (or stdout without it).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
override="${OVERRIDE:-}"

if [ -n "$override" ]; then
  ref="$override"
else
  read -r ref _ <"$root/JTM_REF" || true
fi

if [ -z "${ref:-}" ]; then
  echo "error: JTM_REF is empty" >&2
  exit 1
fi
# A branch, tag or SHA. No leading dash or slash, no "..", nothing a shell or a URL would read
# differently.
if ! [[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || [[ "$ref" == *..* ]]; then
  echo "error: '$ref' is not a usable git ref" >&2
  exit 1
fi

pinned=false
if [[ "$ref" =~ ^[0-9a-f]{40}$ ]]; then
  pinned=true
fi
if [ "${REQUIRE_PINNED:-false}" = "true" ] && [ "$pinned" != "true" ]; then
  echo "error: JTM_REF must be a full commit SHA for publishing (got '$ref')." >&2
  echo "       Edit JTM_REF in a reviewed pull request; see RUNBOOK.md, 'Choosing the jtm revision'." >&2
  exit 1
fi

out="${GITHUB_OUTPUT:-/dev/stdout}"
{
  echo "ref=$ref"
  echo "pinned=$pinned"
} >>"$out"
