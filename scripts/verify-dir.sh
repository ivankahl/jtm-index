#!/usr/bin/env bash
# Checks a directory laid out as a release is, the way a jtm client will: `jtm-index verify`
# over every plugin of the build. It fails with the client's error code when the signing key
# is not delegated to a plugin in keys.json, the delegation has expired, keys.json is not
# signed by the root keys, an index has expired or been altered, or the manifest asks for a
# file name the directory does not hold.
#
#   verify-dir.sh DIR
#
# Environment:
#   JTM_INDEX      the jtm-index binary (default dist/jtm-index)
#   PLUGINS_DIR    the plugin directories of the jtm build (default dist/plugins)
#   ONLY_EXISTING  true: skip plugins that have no file in DIR (the previous release before a
#                  plugin's first publish)
#   NOW            judge expiry as of this UTC time instead of now (recovering from an expired
#                  release: the time it was still valid)
#   MIN_KEY_DAYS   warn when the newest key of a plugin is valid for fewer days (default 14)
#   ROOT_KEYS      space-separated minisign public keys that replace the manifests' root keys.
#                  Only for a rehearsal in a fork with throwaway keys; ignored (and refused) in
#                  the repositories that publish the real indices (jtm-dev/index, ivankahl/jtm-index).
set -euo pipefail

dir="${1:?usage: verify-dir.sh DIR}"
jtm_index="${JTM_INDEX:-dist/jtm-index}"
plugins_dir="${PLUGINS_DIR:-dist/plugins}"

args=(verify --json --published "$dir" --min-key-days "${MIN_KEY_DAYS:-14}")
if [ -n "${NOW:-}" ]; then
  args+=(--now "$NOW")
fi
if [ -n "${ROOT_KEYS:-}" ]; then
  # The repository that publishes the real indices, under the name the jtm SPEC gives it and
  # under the name it has today.
  case "${GITHUB_REPOSITORY:-}" in
    jtm-dev/index | ivankahl/jtm-index)
      echo "error: ROOT_KEYS replaces the root keys and is only for rehearsals in a fork." >&2
      exit 1
      ;;
  esac
  echo "warning: using ROOT_KEYS instead of the manifests' root keys (rehearsal)" >&2
  for key in $ROOT_KEYS; do
    args+=(--root-key "$key")
  done
fi
count=0
for plugin in "$plugins_dir"/*/; do
  [ -f "$plugin/plugin.toml" ] || continue
  name="$(basename "$plugin")"
  if [ "${ONLY_EXISTING:-false}" = "true" ] && ! compgen -G "$dir/$name-*.json" >/dev/null; then
    continue
  fi
  args+=(--plugin-dir "$plugin")
  count=$((count + 1))
done
if [ "$count" -eq 0 ]; then
  echo "error: no plugin to check in $dir" >&2
  exit 1
fi

report="$(mktemp)"
trap 'rm -f "$report"' EXIT
status=0
"$jtm_index" "${args[@]}" >"$report" || status=$?

if jq -e '.ok == true' "$report" >/dev/null 2>&1; then
  jq -r '.data.plugins[] | .plugin as $p | .files[] | "ok \(.file) (sequence \(.sequence), \(.entries) entries, expires \(.expires))"' "$report"
  jq -r '.warnings[]? | "warning[\(.code)]: \(.message)"' "$report" >&2
  if [ -n "${VERIFY_REPORT:-}" ]; then cp -- "$report" "$VERIFY_REPORT"; fi
  exit 0
fi
if jq -e '.error' "$report" >/dev/null 2>&1; then
  jq -r '"error[\(.error.code)]: \(.error.message)"' "$report" >&2
else
  echo "error: jtm-index verify failed with status $status" >&2
fi
exit "$((status == 0 ? 1 : status))"
