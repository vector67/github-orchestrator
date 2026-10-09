import pytest

from github_orchestrator.domain import Repo, Sha
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
