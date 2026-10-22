#!/usr/bin/env bash
# Copies the confirmed files that the update jobs produced into confirmed/.
#
#   stage-confirmed.sh INCOMING_DIR
#
# INCOMING_DIR holds one directory per plugin, `confirmed-<plugin>/<plugin>.json`, as the
# download of the workflow artifacts leaves them. Those files come from jobs that ran code
# built from another repository and read data from the internet, so nothing is trusted: the
# plugin name must be a plain name, the file must be a confirmed file for that plugin, and
# nothing but `confirmed/<plugin>.json` is ever written.
set -euo pipefail

incoming="${1:?usage: stage-confirmed.sh INCOMING_DIR}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$root/confirmed"

staged=0
for dir in "$incoming"/confirmed-*/; do
  [ -d "$dir" ] || continue
  plugin="$(basename "$dir")"
  plugin="${plugin#confirmed-}"
  if ! [[ "$plugin" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "error: '$plugin' is not a plugin name" >&2
    exit 1
  fi
  file="$dir$plugin.json"
  if [ ! -f "$file" ] || [ -L "$file" ]; then
    echo "error: $file is missing or not a regular file" >&2
    exit 1
  fi
  if ! jq -e --arg plugin "$plugin" \
    '.format == 1 and .plugin == $plugin and (.entries | type == "array" and length > 0)' \
    "$file" >/dev/null; then
    echo "error: $file is not a confirmed file for '$plugin'" >&2
    exit 1
  fi
  cp -- "$file" "$root/confirmed/$plugin.json"
  echo "staged confirmed/$plugin.json"
  staged=$((staged + 1))
done

if [ "$staged" -eq 0 ]; then
  echo "nothing to stage"
fi
