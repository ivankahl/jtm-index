#!/usr/bin/env bash
# Decides whether there is anything to release. Needs no secret.
#
#   plan.sh
#
# 1. If a previous release was downloaded to $PREVIOUS_DIR, it is verified like a client would
#    (verify-dir.sh), because its sequences are about to be continued and a file that does not
#    verify must not raise them.
# 2. generate-all.sh plan: a dry run per plugin from confirmed/, against that release.
# 3. Release when any plugin would get a new index file, or when keys/keys.json is not the one
#    the previous release carries.
#
# Writes `changed=<true|false>` and `has_previous=<true|false>` to $GITHUB_OUTPUT and a short
# summary to $GITHUB_STEP_SUMMARY.
#
# Environment: PREVIOUS_DIR (default previous; may be missing or empty for a first release),
# PREVIOUS_AS_OF (optional, see below), FORCE (true: release even when nothing differs, for
# example to sign unchanged files with a new key), REPORT_DIR (default reports), and those of
# generate-all.sh and verify-dir.sh.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
previous_dir="${PREVIOUS_DIR:-previous}"
report_dir="${REPORT_DIR:-reports}"
out="${GITHUB_OUTPUT:-/dev/stdout}"
summary="${GITHUB_STEP_SUMMARY:-/dev/null}"

for file in keys.json keys.json.minisig; do
  if [ ! -f "$root/keys/$file" ]; then
    echo "error: keys/$file does not exist, so nothing can be released." >&2
    echo "       It comes from the root key ceremony; see RUNBOOK.md, 'Keys'." >&2
    exit 1
  fi
done

has_previous=false
if [ -d "$previous_dir" ] && compgen -G "$previous_dir/*.json" >/dev/null; then
  has_previous=true
  # PREVIOUS_AS_OF judges expiry as of a time the release was still valid, to recover from a
  # release that expired before this ran (RUNBOOK.md, 'Recovering from an expired release').
  ONLY_EXISTING=true NOW="${PREVIOUS_AS_OF:-}" "$root/scripts/verify-dir.sh" "$previous_dir"
  export PREVIOUS_DIR="$previous_dir"
else
  unset PREVIOUS_DIR
  echo "no previous release: this is a first publish"
fi

"$root/scripts/generate-all.sh" plan

changed=false
{
  echo "### Release plan"
  echo
} >>"$summary"
for report in "$report_dir"/*.json; do
  plugin="$(basename "$report" .json)"
  if jq -e '.data.changed == true' "$report" >/dev/null; then
    changed=true
    echo "- \`$plugin\`: new index files ($(jq -r '[.data.files[] | select(.action != "unchanged") | .file] | join(", ")' "$report"))" >>"$summary"
  else
    echo "- \`$plugin\`: unchanged" >>"$summary"
  fi
  jq -r '.warnings[]? | "warning[\(.code)]: \(.message)"' "$report" >&2
done

if [ "${FORCE:-false}" = "true" ]; then
  # A dry run has no signing key, so it cannot tell that a new key would sign the unchanged
  # files again. After the signing key secret changes, a person forces a release.
  changed=true
  echo "- release forced by a person" >>"$summary"
fi

if [ "$has_previous" = "true" ]; then
  for file in keys.json keys.json.minisig; do
    if ! cmp -s "$root/keys/$file" "$previous_dir/$file"; then
      changed=true
      echo "- \`$file\` differs from the previous release" >>"$summary"
    fi
  done
else
  changed=true
  echo "- first release" >>"$summary"
fi

{
  echo "changed=$changed"
  echo "has_previous=$has_previous"
} >>"$out"
echo "release needed: $changed"
