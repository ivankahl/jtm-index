#!/usr/bin/env bash
# Runs `jtm-index generate` for every plugin, from the reviewed files in confirmed/.
#
#   generate-all.sh plan|sign
#
# plan  A dry run: nothing is signed or written, and no secret is needed. It reports which
#       plugins would get a new index file, so the publish job (and its approval) only
#       happens when there is something to release.
# sign  The real run: signs with the key in the environment and writes the files into
#       $RELEASE_DIR.
#
# Environment:
#   JTM_INDEX       the jtm-index binary (default dist/jtm-index)
#   PLUGINS_DIR     the plugin directories of the jtm build (default dist/plugins)
#   REPORT_DIR      where each plugin's JSON report goes (default reports)
#   RELEASE_DIR     sign only: where the signed files go (default release)
#   PREVIOUS_DIR    the verified previous release, if there is one
#   JTM_INDEX_SIGNING_KEY, JTM_INDEX_SIGNING_KEY_PASSWORD
#                   sign only: the contents of the minisign key file and its password
#
# The key and the password are only ever named to jtm-index (`--secret-key-env`,
# `--password-env`); they are not on any command line, not echoed, and tracing is off.
set -euo pipefail
set +x

mode="${1:?usage: generate-all.sh plan|sign}"
case "$mode" in plan | sign) ;; *)
  echo "usage: generate-all.sh plan|sign" >&2
  exit 2
  ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jtm_index="${JTM_INDEX:-dist/jtm-index}"
plugins_dir="${PLUGINS_DIR:-dist/plugins}"
report_dir="${REPORT_DIR:-reports}"
release_dir="${RELEASE_DIR:-release}"
previous_dir="${PREVIOUS_DIR:-}"

mkdir -p "$report_dir"
rm -f "$report_dir"/*.json

# The delegated keys of the previous release sign its indices. The release was verified
# against the root keys (verify-previous.sh) before this runs, so its keys.json is trustworthy.
previous_keys=()
if [ -n "$previous_dir" ] && [ -f "$previous_dir/keys.json" ]; then
  while IFS= read -r key; do
    previous_keys+=(--previous-key "$key")
  done < <(jq -r '.keys[].key' "$previous_dir/keys.json")
fi

signing=()
if [ "$mode" = "sign" ]; then
  if [ -z "${JTM_INDEX_SIGNING_KEY:-}" ]; then
    echo "error: JTM_INDEX_SIGNING_KEY is not set (see RUNBOOK.md, 'Secrets')" >&2
    exit 1
  fi
  signing=(--secret-key-env JTM_INDEX_SIGNING_KEY --out "$release_dir")
  if [ -n "${JTM_INDEX_SIGNING_KEY_PASSWORD:-}" ]; then
    signing+=(--password-env JTM_INDEX_SIGNING_KEY_PASSWORD)
  fi
  mkdir -p "$release_dir"
else
  signing=(--dry-run --out "${RUNNER_TEMP:-/tmp}/jtm-index-unused")
fi

failed=0
found=0
for dir in "$plugins_dir"/*/; do
  [ -f "$dir/plugin.toml" ] || continue
  plugin="$(basename "$dir")"
  found=$((found + 1))
  confirmed="$root/confirmed/$plugin.json"
  if [ ! -f "$confirmed" ]; then
    echo "error: confirmed/$plugin.json does not exist. Run the 'Update' workflow and merge its pull request first." >&2
    failed=1
    continue
  fi
  args=(generate --json --plugin-dir "$dir" --use-confirmed "$confirmed" "${signing[@]}")
  # A plugin that has no file in the previous release yet is a first publish for it.
  if [ -n "$previous_dir" ] && compgen -G "$previous_dir/$plugin-*.json" >/dev/null; then
    args+=(--previous "$previous_dir" "${previous_keys[@]}")
  fi
  echo "== $plugin ($mode)"
  if ! "$jtm_index" "${args[@]}" >"$report_dir/$plugin.json" 2>"$report_dir/$plugin.log"; then
    failed=1
  fi
  # Warnings and errors, never anything else: the log holds what jtm-index sent to stderr.
  sed 's/^/   /' "$report_dir/$plugin.log" >&2
  if jq -e '.ok == false' "$report_dir/$plugin.json" >/dev/null 2>&1; then
    jq -r '"   error[\(.error.code)]: \(.error.message)"' "$report_dir/$plugin.json" >&2
    failed=1
  fi
done

if [ "$found" -eq 0 ]; then
  echo "error: no plugin directories in $plugins_dir" >&2
  exit 1
fi
exit "$failed"
