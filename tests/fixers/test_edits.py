import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from allymend.core.models import Edit
from allymend.fixers import apply_edits, unified_diff

GIT = shutil.which("git")


def edit(start: int, end: int, text: str, file: str = "index.html") -> Edit:
    return Edit(file=file, start=start, end=end, text=text)


def test_applies_insertions_replacements_and_deletions_in_any_order() -> None:
    text = "<html><title>Shop</title><b>Sale</b>"
    edits = [
        edit(text.index("<b>"), len(text), ""),
        edit(5, 5, ' lang="en"'),
        edit(text.index("Shop"), text.index("Shop") + 4, "Harbor Goods"),
    ]
    assert apply_edits(text, edits) == '<html lang="en"><title>Harbor Goods</title>'


def test_edits_may_touch_without_overlapping() -> None:
    assert apply_edits("abcd", [edit(2, 2, "+"), edit(0, 2, "AB")]) == "AB+cd"


def test_no_edits_leave_the_text_alone() -> None:
    assert apply_edits("<html>", []) == "<html>"


@pytest.mark.parametrize(
    ("edits", "message"),
    [
        ([edit(0, 3, "x"), edit(2, 4, "y")], "edits at 0-3 and 2-4 in index.html overlap"),
        ([edit(1, 1, "x"), edit(1, 1, "y")], "edits at 1-1 and 1-1 in index.html overlap"),
        ([edit(1, 1, "x"), edit(1, 3, "y")], "edits at 1-1 and 1-3 in index.html overlap"),
        ([edit(2, 9, "x")], "edit 2-9 lies outside the 6 characters of index.html"),
        ([edit(-1, 0, "x")], "edit -1-0 lies outside the 6 characters of index.html"),
        ([edit(3, 2, "x")], "edit 3-2 lies outside the 6 characters of index.html"),
        (
            [edit(0, 0, "x"), edit(2, 2, "y", file="about.html")],
            "edits for more than one file can't be applied to one text",
        ),
    ],
    ids=[
        "overlap",
        "same-insertion-point",
        "insertion-at-a-replacement",
        "past-the-end",
        "negative",
        "backwards",
        "two-files",
    ],
)
def test_rejects_edits_that_cannot_be_applied_safely(edits: list[Edit], message: str) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        apply_edits("<html>", edits)


def test_unified_diff_shows_the_changed_lines_with_context() -> None:
    before = "<!doctype html>\n<html>\n<title>Shop</title>\n"
    after = '<!doctype html>\n<html lang="en">\n<title>Shop</title>\n'
    assert unified_diff("shop/index.html", before, after) == (
        "--- a/shop/index.html\n"
        "+++ b/shop/index.html\n"
        "@@ -1,3 +1,3 @@\n"
        " <!doctype html>\n"
        "-<html>\n"
        '+<html lang="en">\n'
        " <title>Shop</title>\n"
    )


def test_unified_diff_marks_a_last_line_without_a_newline() -> None:
    assert unified_diff("index.html", "<html>", '<html lang="en">') == (
        "--- a/index.html\n"
        "+++ b/index.html\n"
        "@@ -1 +1 @@\n"
        "-<html>\n"
        "\\ No newline at end of file\n"
        '+<html lang="en">\n'
        "\\ No newline at end of file\n"
    )


def test_unified_diff_is_empty_when_nothing_changed() -> None:
    assert unified_diff("index.html", "<html>\n", "<html>\n") == ""


@pytest.mark.skipif(GIT is None, reason="git is not installed")
@pytest.mark.parametrize(
    ("file", "before"),
    [
        ("index.html", "<!doctype html>\n<html>\n<title>Shop</title>\n"),
        ("index.html", "<!doctype html>\r\n<html>\r\n<title>Shop</title>\r\n"),
        ("index.html", "<!doctype html>\r<html>\r<title>Shop</title>"),
        ("index.html", "<!doctype html><html><title>Shop</title>"),
        ("index.html", "\ufeff<!doctype html>\n<html>\n"),
        ("index.html", "<p>a\x0cb\u2028c\x85d</p>\n<html>\n"),
        ("shop/blue mug.html", "<html>\n"),
        ("parduotuvė/žąsis.html", "<html>\n"),
    ],
    ids=[
        "lf",
        "crlf",
        "lone-cr",
        "no-final-newline",
        "byte-order-mark",
        "unusual-line-breaks",
        "space-in-name",
        "non-ascii-name",
    ],
)
def test_git_applies_the_diff_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file: str, before: str
) -> None:
    # Settings like core.autocrlf on the machine running the tests would rewrite line endings.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    path = tmp_path / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(before.encode("utf-8"))
    insert_at = before.index("<html") + len("<html")
    after = apply_edits(before, [edit(insert_at, insert_at, ' lang="en"', file=file)])
    patch = tmp_path / "fix.patch"
    patch.write_bytes(unified_diff(file, before, after).encode("utf-8"))

    git(tmp_path, "init", "--quiet")
    git(tmp_path, "apply", patch.name)

    assert path.read_bytes() == after.encode("utf-8")


def git(cwd: Path, *args: str) -> None:
    assert GIT is not None
    subprocess.run([GIT, *args], cwd=cwd, check=True)  # noqa: S603  fixed arguments in a test
