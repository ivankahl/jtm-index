#!/usr/bin/env python3
"""Release notes and the release tag, from the reports `jtm-index generate --json` printed.

    release_notes.py notes --reports DIR --jtm-ref REF --run-url URL
    release_notes.py max-sequence --reports DIR

DIR holds one `<plugin>.json` envelope per plugin. `notes` prints the Markdown for the release
body; `max-sequence` prints the highest index sequence in the release, which goes into the tag
(`index-<UTC time>-seq<N>`). Nothing here reads a file other than the reports.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SAFE = re.compile(r"[^A-Za-z0-9._+:/=-]")


def safe(value):
    return SAFE.sub("_", str(value))[:120]


def reports(directory):
    found = []
    for path in sorted(Path(directory).glob("*.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not envelope.get("ok"):
            raise SystemExit(f"{path.name}: the report is not a success")
        found.append(envelope["data"])
    if not found:
        raise SystemExit(f"no reports in {directory}")
    return found


def max_sequence(data):
    return max(f["sequence"] for plugin in data for f in plugin["files"])


def notes(data, jtm_ref, run_url):
    lines = [
        "Signed jtm version indices. Every release holds every index, `keys.json` and the "
        "signatures, so the newest release is a complete copy: jtm reads "
        "`releases/latest/download/<file>`.",
        "",
        "| file | action | sequence | entries | expires |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for plugin in data:
        for f in plugin["files"]:
            lines.append(
                f"| `{safe(f['file'])}` | {safe(f['action'])} | {int(f['sequence'])} "
                f"| {int(f['entries'])} | {safe(f['expires'])} |"
            )
    lines += [
        "",
        f"Built with jtm-index from `{safe(jtm_ref)}`. Workflow run: {safe(run_url)}",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    n = sub.add_parser("notes")
    n.add_argument("--reports", required=True)
    n.add_argument("--jtm-ref", required=True)
    n.add_argument("--run-url", required=True)
    m = sub.add_parser("max-sequence")
    m.add_argument("--reports", required=True)
    args = parser.parse_args(argv)
    data = reports(args.reports)
    if args.command == "notes":
        sys.stdout.write(notes(data, args.jtm_ref, args.run_url))
    else:
        print(max_sequence(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
