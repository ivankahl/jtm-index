#!/usr/bin/env python3
"""Describe what changed between two directories of confirmed files, as Markdown.

    changelog.py OLD_DIR NEW_DIR [--reports DIR] [--max-chars N]

Each directory holds `<plugin>.json` files written by `jtm-index generate
--write-confirmed`. The output is the body of the pull request that proposes the new files:
per plugin, the versions added, the versions removed, and every version whose SHA-256
changed (which clients holding a lockfile for it will refuse, so a person must look at it).

With --reports, the warnings the sources raised (`<plugin>.report.json` files under DIR, the
output of `jtm-index generate --json`) are listed after the changes.

Nothing from the files reaches a shell. Values are cut down to a safe alphabet before they
go into the Markdown, so an odd string from an upstream cannot add links, mentions or markup.
Prints nothing when nothing changed.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# GitHub rejects a pull request body longer than 65536 characters.
DEFAULT_MAX_CHARS = 60000
SAFE = re.compile(r"[^A-Za-z0-9._+:=-]")
# Warning messages are sentences: letters, digits, spaces and a little punctuation.
SAFE_TEXT = re.compile(r"[^A-Za-z0-9 ._+:=,()'/-]")


def safe(value):
    """A value cut down to characters that cannot form Markdown, HTML, links or mentions."""
    return SAFE.sub("_", str(value))[:80]


def safe_text(value, limit=300):
    return SAFE_TEXT.sub("_", str(value))[:limit]


def load_notes(directory):
    """The warnings in every `<plugin>.report.json` under `directory`, as (plugin, code, message)."""
    notes = []
    for path in sorted(Path(directory).rglob("*.report.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        plugin = path.name[: -len(".report.json")]
        for warning in envelope.get("warnings") or []:
            notes.append((plugin, warning.get("code", ""), warning.get("message", "")))
    return notes


def notes_section(notes, limit=60):
    if not notes:
        return None
    lines = ["### Notes from the sources", ""]
    for plugin, code, message in notes[:limit]:
        # In a code span, a URL in the text is not linked and a name is not mentioned.
        lines.append(f"- `{safe(plugin)}` `{safe(code)}`: `{safe_text(message)}`")
    if len(notes) > limit:
        lines.append(f"- _{len(notes) - limit} more are in the workflow log._")
    lines.append("")
    return "\n".join(lines)


def load(directory):
    """Maps plugin name to {(variant, version, platform): entry}."""
    plugins = {}
    for path in sorted(Path(directory).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = {}
        for entry in data["entries"]:
            key = (entry.get("variant", ""), entry["version"], entry["platform"])
            entries[key] = entry
        plugins[path.stem] = entries
    return plugins


def diff(old, new):
    added = sorted(k for k in new if k not in old)
    removed = sorted(k for k in old if k not in new)
    changed = sorted(k for k in new if k in old and old[k]["sha256"] != new[k]["sha256"])
    return added, removed, changed


def group(keys):
    """(variant, version) -> platforms."""
    grouped = defaultdict(list)
    for variant, version, platform in keys:
        grouped[(variant, version)].append(platform)
    return grouped


def version_label(variant, version):
    return f"{safe(variant)} {safe(version)}".strip()


def plugin_section(name, old, new, room):
    """The Markdown for one plugin, or None when nothing changed. `room` caps the table rows."""
    added, removed, changed = diff(old, new)
    if not (added or removed or changed):
        return None
    lines = [f"### {safe(name)}", ""]
    counts = (
        f"{len(added)} added, {len(removed)} removed, {len(changed)} with a changed SHA-256"
        " (counted per platform)"
    )
    lines += [counts, ""]
    if changed:
        lines += [
            "**A version listed again with a different SHA-256.** Clients with a lockfile for "
            "it will refuse the new index (`E_LOCK_INDEX_MISMATCH`). Treat this as an attack "
            "until the vendor explains it.",
            "",
            "| version | platform | old SHA-256 | new SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
        for variant, version, platform in changed:
            key = (variant, version, platform)
            lines.append(
                f"| `{version_label(variant, version)}` | `{safe(platform)}` "
                f"| `{safe(old[key]['sha256'])}` | `{safe(new[key]['sha256'])}` |"
            )
        lines.append("")
    if added:
        lines += ["<details><summary>Added</summary>", ""]
        lines += ["| version | platform | size | SHA-256 | confirmed by |", "| --- | --- | ---: | --- | --- |"]
        shown = 0
        for key in added:
            if shown >= room:
                break
            entry = new[key]
            variant, version, platform = key
            provenance = ", ".join(safe(p) for p in entry["provenance"])
            lines.append(
                f"| `{version_label(variant, version)}` | `{safe(platform)}` | {int(entry['size'])} "
                f"| `{safe(entry['sha256'])}` | {provenance} |"
            )
            shown += 1
        if shown < len(added):
            lines += ["", f"_{len(added) - shown} more rows are in the diff of the file._"]
        lines += ["", "</details>", ""]
    if removed:
        lines += ["<details><summary>Removed</summary>", ""]
        for (variant, version), platforms in sorted(group(removed).items()):
            lines.append(
                f"- `{version_label(variant, version)}` on {', '.join(safe(p) for p in sorted(platforms))}"
            )
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def render(old, new, max_chars=DEFAULT_MAX_CHARS, notes=()):
    names = sorted(set(old) | set(new))
    header = [
        "Proposed by the scheduled update. Review the diff of `confirmed/`: it is exactly what the "
        "publish workflow will sign after this is merged.",
        "",
    ]
    # Spread the room for table rows over the plugins; the footer says when rows were left out.
    rows = 400
    while True:
        sections = []
        for name in names:
            section = plugin_section(name, old.get(name, {}), new.get(name, {}), rows)
            if section is not None:
                sections.append(section)
        if not sections:
            return ""
        extra = notes_section(list(notes))
        if extra is not None:
            sections.append(extra)
        body = "\n".join(header + sections)
        if len(body) <= max_chars or rows <= 1:
            return body[:max_chars]
        rows //= 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("old_dir")
    parser.add_argument("new_dir")
    parser.add_argument("--reports")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    args = parser.parse_args(argv)
    notes = load_notes(args.reports) if args.reports else []
    body = render(load(args.old_dir), load(args.new_dir), args.max_chars, notes)
    if body:
        sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
