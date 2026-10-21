from leak_check import Finding, findings

DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 CONFIG = "/Users/octocat/.config"
-OLD = "/home/someone/old"
+NEW = "/Users/jdoe/work/app"
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
+Ask Bob at Initech about it.
"""


def test_an_added_home_path_is_found_with_its_file() -> None:
    assert Finding("home path", "src/app.py", 'NEW = "/Users/jdoe/work/app"') in findings({}, DIFF, [])


def test_removed_and_context_lines_are_not_reported() -> None:
    texts = [found.text for found in findings({}, DIFF, [])]
    assert not any("octocat" in text or "someone" in text for text in texts)


def test_a_denylisted_term_is_found_in_a_diff_and_a_message_whatever_its_case() -> None:
    found = findings({"abc1234": "fix the initech export"}, DIFF, ["Initech"])
    assert Finding("denylisted: Initech", "README.md", "Ask Bob at Initech about it.") in found
    assert Finding("denylisted: Initech", "commit abc1234", "fix the initech export") in found


def test_a_denylisted_term_matches_only_as_a_whole_word() -> None:
    assert findings({"abc1234": "the acmeish widget"}, "", ["acme"]) == []


def test_a_real_shaped_token_is_found_but_a_short_fake_one_is_not() -> None:
    real = "gho_" + "a1B2" * 9
    found = findings({"abc1234": f"token {real}\nfake gho_anna"}, "", [])
    assert [finding.text for finding in found] == [f"token {real}"]


def test_an_email_is_found_but_github_noreply_and_example_addresses_are_not() -> None:
    message = "by jane.doe@initech.com\nCo-authored: 1+octocat@users.noreply.github.com\nsee ops@example.com"
    assert [finding.text for finding in findings({"abc1234": message}, "", [])] == ["by jane.doe@initech.com"]


def test_a_clean_range_finds_nothing() -> None:
    assert findings({"abc1234": "add a button"}, "+++ b/x.py\n+print('hi')\n", ["Initech"]) == []


def test_an_added_line_starting_with_two_pluses_is_scanned() -> None:
    diff = "diff --git a/notes.md b/notes.md\n--- a/notes.md\n+++ b/notes.md\n@@ -0,0 +1 @@\n+++ see /Users/jdoe/notes\n"
    assert findings({}, diff, []) == [Finding("home path", "notes.md", "++ see /Users/jdoe/notes")]
