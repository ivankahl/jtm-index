#!/usr/bin/env bash
# Completes the release directory and checks it before anything is published.
#
#   assemble-release.sh
#
# Adds keys/keys.json and its signature to the signed index files in $RELEASE_DIR, so the
# newest release is a complete copy (clients read releases/latest/download/<file>), then runs
# verify-dir.sh over the result. That is the pre-publish check: it fails unless a jtm client
# would accept every file, which includes the signing key being delegated to each plugin in
# keys.json and not expired.
#
# Environment: RELEASE_DIR (default release), and those of verify-dir.sh.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
release_dir="${RELEASE_DIR:-release}"

for file in keys.json keys.json.minisig; do
  if [ ! -f "$root/keys/$file" ]; then
    echo "error: keys/$file does not exist." >&2
    echo "       It is produced by the root key ceremony (jtm docs/key-ceremony.md) and committed" >&2
    echo "       in a reviewed pull request. See RUNBOOK.md, 'Keys'." >&2
    exit 1
  fi
  cp -- "$root/keys/$file" "$release_dir/$file"
done

"$root/scripts/verify-dir.sh" "$release_dir"

# Every file of a release is an index file with its signature, or one of the keys files.
# Anything else in the directory would be uploaded as an asset.
for path in "$release_dir"/*; do
  name="$(basename "$path")"
  case "$name" in
    keys.json | keys.json.minisig) ;;
    *.json) [ -f "$path.minisig" ] || {
      echo "error: $name has no .minisig" >&2
      exit 1
    } ;;
    *.json.minisig) [ -f "${path%.minisig}" ] || {
      echo "error: $name has no index file" >&2
      exit 1
    } ;;
    *)
      echo "error: unexpected file $name in the release" >&2
      exit 1
      ;;
  esac
done
