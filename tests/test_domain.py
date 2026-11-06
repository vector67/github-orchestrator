import pytest

from github_orchestrator.domain import Repo, Sha, ThreadName
from tests.builders import a_pr


@pytest.mark.parametrize("text", ["octocat/hello", "a_b/c-d", "x/y.z",
                                  "acme/widgets", "a.b/c..d"])
def test_a_repo_of_ordinary_name_characters_parses_back_to_the_same_text(text):
    assert str(Repo.parse(text)) == text


def test_a_parsed_repo_knows_its_owner_and_name():
    repo = Repo.parse("acme/widgets")

    assert (repo.owner, repo.name) == ("acme", "widgets")


@pytest.mark.parametrize("text", ["", "no-slash", "/leading", "trailing/", "a/b/c",
                                  "../x", "..%2F../x", "../..", ".././x", "a/..", ".",
                                  "a/.", "./x", "a b/c", "a\\b/c", "a/b c",
                                  "a;rm -rf/c", "a/b;rm -rf /"])
def test_anything_but_a_plain_owner_and_name_is_refused(text):
    with pytest.raises(ValueError, match="owner/name"):
        Repo.parse(text)


def test_a_repo_cannot_be_built_around_the_parse():
    with pytest.raises(ValueError, match="owner/name"):
        Repo("..", "x")


def test_a_pr_is_spelled_owner_name_hash_number():
    assert str(a_pr(42, "acme/widgets")) == "acme/widgets#42"


def test_a_pr_is_spelled_short_as_its_repo_name_hash_number():
    assert a_pr(42, "acme/widgets").short == "widgets#42"


def test_within_its_repo_a_pr_is_spelled_hash_number():
    assert a_pr(42, "acme/widgets").in_repo == "#42"


def test_prs_sort_by_repo_then_number():
    one, two, other = (a_pr(2, "a/b"), a_pr(10, "a/b"),
                       a_pr(1, "a/c"))

    assert sorted([other, two, one]) == [one, two, other]


@pytest.mark.parametrize("text", ["abc1234", "a" * 40, "ABCDEF0"])
def test_a_commit_hash_of_seven_to_forty_hex_digits_parses_back_to_the_same_text(text):
    assert str(Sha.parse(text)) == text


@pytest.mark.parametrize("text", [None, "", "abc123", "a" * 41, "z" * 40, "HEAD",
                                  "--output=/tmp/pwned", "-p", "abc1234 "])
def test_anything_else_is_no_commit_hash(text):
    assert Sha.parse(text) is None


def test_a_commit_hash_is_not_made_of_anything_else():
    with pytest.raises(ValueError):
        Sha("HEAD")


@pytest.mark.parametrize(("key", "name"), [
    ("PRRT_abcR", "PRRT_abcR-f1"),
    ("PRRT_abcr", "PRRT_abcr-f0"),
    ("MDI0OlB1bGx/UmV2aWV3=", "MDI0OlB1bGx%2FUmV2aWV3%3D-7aab"),
    ("..PRRT_kwDO", "..PRRT_kwDO-f3"),
    ("12", "12-0"),
])
def test_a_thread_key_names_its_files_quoted_then_by_which_letters_are_capitals(key, name):
    assert str(ThreadName(key)) == name


@pytest.mark.parametrize("key", ["PRRT_abcR", "a/b", "a%2Fb", "..x", "état-1"])
def test_a_thread_name_parses_back_to_its_key(key):
    assert ThreadName.parse(str(ThreadName(key))) == ThreadName(key)


@pytest.mark.parametrize("key", ["", ".", ".."])
def test_a_key_that_names_no_file_of_its_own_is_no_thread_name(key):
    with pytest.raises(ValueError):
        ThreadName(key)


@pytest.mark.parametrize("name", ["PRRT_abcR", "PRRT_abcR-f0", "%73tate-0", "%2E%2E-0", "-0", ""])
def test_a_name_no_thread_key_spells_parses_to_nothing(name):
    assert ThreadName.parse(name) is None
