"""Tests for the helper scripts. Run with `python3 -m unittest discover -s scripts`."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import changelog  # noqa: E402
import release_notes  # noqa: E402

A = "a" * 64
B = "b" * 64
C = "c" * 64


def entry(version, platform="linux-x64", sha=A, variant="temurin", provenance=("adoptium-api", "github-sidecar")):
    return {
        "variant": variant,
        "version": version,
        "platform": platform,
        "tags": ["ga"],
        "url": "https://vendor.example/x.tar.gz",
        "archive": "tar.gz",
        "size": 1234,
        "sha256": sha,
        "provenance": list(provenance),
    }


def confirmed(plugin, *entries):
    return {"format": 1, "plugin": plugin, "entries": list(entries)}


class Dirs:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def write(self, side, plugin, *entries):
        directory = self.root / side
        directory.mkdir(exist_ok=True)
        (directory / f"{plugin}.json").write_text(json.dumps(confirmed(plugin, *entries)))
        return directory

    def path(self, side):
        return self.root / side

    def close(self):
        self._tmp.cleanup()


class ChangelogTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs()
        self.addCleanup(self.dirs.close)

    def render(self, **kwargs):
        return changelog.render(
            changelog.load(self.dirs.path("old")), changelog.load(self.dirs.path("new")), **kwargs
        )

    def test_nothing_changed_gives_nothing(self):
        self.dirs.write("old", "java", entry("21.0.5+11"))
        self.dirs.write("new", "java", entry("21.0.5+11"))
        self.assertEqual(self.render(), "")

    def test_an_added_version_is_listed_with_its_hash_and_provenance(self):
        self.dirs.write("old", "java", entry("21.0.5+11"))
        self.dirs.write("new", "java", entry("21.0.5+11"), entry("21.0.6+7", sha=B))
        body = self.render()
        self.assertIn("### java", body)
        self.assertIn("1 added, 0 removed, 0 with a changed SHA-256", body)
        self.assertIn("`temurin 21.0.6+7`", body)
        self.assertIn(B, body)
        self.assertIn("adoptium-api, github-sidecar", body)
        self.assertNotIn("A version listed again", body)

    def test_a_removed_version_is_listed_by_platform(self):
        self.dirs.write("old", "java", entry("8.0.1+1"), entry("8.0.1+1", platform="windows-x64"))
        self.dirs.write("new", "java", entry("21.0.5+11"))
        body = self.render()
        self.assertIn("2 removed", body)
        self.assertIn("`temurin 8.0.1+1` on linux-x64, windows-x64", body)

    def test_a_changed_hash_is_called_out_with_both_hashes(self):
        self.dirs.write("old", "java", entry("21.0.5+11", sha=A))
        self.dirs.write("new", "java", entry("21.0.5+11", sha=C))
        body = self.render()
        self.assertIn("A version listed again with a different SHA-256", body)
        self.assertIn(A, body)
        self.assertIn(C, body)
        self.assertIn("E_LOCK_INDEX_MISMATCH", body)

    def test_a_new_plugin_is_all_additions(self):
        self.dirs.write("old", "java", entry("21.0.5+11"))
        self.dirs.write("new", "java", entry("21.0.5+11"))
        self.dirs.write("new", "maven", entry("3.9.9", platform="any", variant=""))
        body = self.render()
        self.assertIn("### maven", body)
        self.assertNotIn("### java", body)
        self.assertIn("`3.9.9`", body)

    def test_upstream_text_cannot_add_markup_or_mentions(self):
        self.dirs.write("old", "java", entry("1"))
        nasty = entry("1.0", provenance=("[x](http://evil)", "@someone", "<img src=x>", "`"))
        self.dirs.write("new", "java", nasty)
        body = self.render()
        for bad in ("[x](", "@someone", "<img", "http://evil"):
            self.assertNotIn(bad, body)

    def test_a_long_list_is_cut_to_the_limit_and_says_so(self):
        many = [entry(f"1.{i}", sha=f"{i:064x}") for i in range(2000)]
        self.dirs.write("old", "java", entry("0.1"))
        self.dirs.write("new", "java", entry("0.1"), *many)
        body = self.render(max_chars=20000)
        self.assertLessEqual(len(body), 20000)
        self.assertIn("more rows are in the diff of the file", body)

    def test_warnings_of_the_sources_follow_the_changes_and_are_made_safe(self):
        self.dirs.write("old", "java", entry("1"))
        self.dirs.write("new", "java", entry("1"), entry("2"))
        reports = self.dirs.path("reports") / "report-java"
        reports.mkdir(parents=True)
        (reports / "java.report.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "warnings": [
                        {"code": "W_SOURCE_NOTE", "message": "kotlin 1.0 has no sidecar [x](http://evil) @someone"}
                    ],
                }
            )
        )
        body = self.render(notes=changelog.load_notes(self.dirs.path("reports")))
        self.assertIn("### Notes from the sources", body)
        self.assertIn("`W_SOURCE_NOTE`", body)
        self.assertIn("`kotlin 1.0 has no sidecar _x_(http://evil) _someone`", body)
        for bad in ("[x]", "@someone"):
            self.assertNotIn(bad, body)

    def test_notes_alone_do_not_open_a_pull_request(self):
        self.dirs.write("old", "java", entry("1"))
        self.dirs.write("new", "java", entry("1"))
        notes = [("java", "W_SOURCE_NOTE", "something")]
        self.assertEqual(self.render(notes=notes), "")

    def test_the_command_prints_the_body_or_nothing(self):
        self.dirs.write("old", "java", entry("1"))
        self.dirs.write("new", "java", entry("1"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            changelog.main([str(self.dirs.path("old")), str(self.dirs.path("new"))])
        self.assertEqual(out.getvalue(), "")
        self.dirs.write("new", "java", entry("1"), entry("2"))
        with contextlib.redirect_stdout(out):
            changelog.main([str(self.dirs.path("old")), str(self.dirs.path("new"))])
        self.assertIn("### java", out.getvalue())


def report(plugin, *files):
    return {
        "ok": True,
        "command": "generate",
        "data": {
            "plugin": plugin,
            "files": [
                {"file": f"{plugin}-{p}.json", "action": a, "sequence": s, "entries": 3, "expires": "2026-11-18T03:00:00Z"}
                for (p, a, s) in files
            ],
        },
    }


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def put(self, name, envelope):
        (self.dir / f"{name}.json").write_text(json.dumps(envelope))

    def test_max_sequence_is_the_highest_across_plugins(self):
        self.put("java", report("java", ("linux-x64", "updated", 7), ("windows-x64", "unchanged", 9)))
        self.put("maven", report("maven", ("any", "created", 1)))
        self.assertEqual(release_notes.max_sequence(release_notes.reports(self.dir)), 9)

    def test_notes_list_every_file_and_the_build(self):
        self.put("maven", report("maven", ("any", "created", 1)))
        text = release_notes.notes(release_notes.reports(self.dir), "abc123", "https://github.com/o/r/actions/runs/1")
        self.assertIn("`maven-any.json` | created | 1 | 3 |", text)
        self.assertIn("releases/latest/download", text)
        self.assertIn("abc123", text)

    def test_a_failed_report_stops_the_release(self):
        self.put("java", {"ok": False, "error": {"code": "E_USAGE"}})
        with self.assertRaises(SystemExit):
            release_notes.reports(self.dir)

    def test_no_reports_stops_the_release(self):
        with self.assertRaises(SystemExit):
            release_notes.reports(self.dir)


if __name__ == "__main__":
    unittest.main()
