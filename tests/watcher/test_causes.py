import json

import pytest

from github_orchestrator.domain import Cause, Repo
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from tests.watcher.support import health

REAL_ERRORS = [
    ('Post "https://api.github.com/graphql": dial tcp: lookup api.github.com: no such host',
     Cause.NETWORK),
    ('Post "https://api.github.com/graphql": net/http: TLS handshake timeout', Cause.NETWORK),
    ('Post "https://api.github.com/graphql": unexpected EOF', Cause.NETWORK),
    ("read tcp 10.0.0.2:51234->140.82.112.6:443: read: connection reset by peer",
     Cause.NETWORK),
    ('Get "https://api.github.com/user": dial tcp 140.82.112.6:443: i/o timeout', Cause.NETWORK),
    ("gh search prs failed (exit 1): HTTP 502: Bad Gateway (https://api.github.com/graphql)",
     Cause.NETWORK),
    ("HTTP 403: You have exceeded a secondary rate limit. Please wait a few minutes "
     "before you try again.", Cause.NETWORK),
    ("GraphQL: was submitted too quickly (createPullRequestReview)", Cause.NETWORK),
    ("HTTP 401: Bad credentials (https://api.github.com/graphql)", Cause.OPERATOR),
    ("gh auth token --user octocat failed (exit 1): no oauth token found for github.com "
     "account octocat", Cause.OPERATOR),
    ("HTTP 403: Resource not accessible by integration "
     "(https://api.github.com/repos/acme/widgets/pulls)", Cause.OPERATOR),
    ("gh: Not Found (HTTP 404)", Cause.OPERATOR),
    ("gh search prs failed (exit 1): Invalid search query. The listed users and repositories "
     "cannot be searched either because the resources do not exist or you do not have "
     "permission to view them.", Cause.OPERATOR),
    ("[Errno 28] No space left on device: '/data/github-orchestrator/state.json'",
     Cause.OPERATOR),
    ("config.toml: mentions_start must be in quotes", Cause.OPERATOR),
    ("poll blew up", Cause.OPERATOR),
]


def _failing(path, error, fix=None):
    path.write_text(json.dumps({"consecutive": 2, "last_error": error, "fix": fix}))


@pytest.mark.parametrize(("error", "cause"), REAL_ERRORS)
def test_a_failing_poll_names_whether_the_network_or_the_operator_must_clear_it(
        settings, error, cause):
    _failing(settings.watcher_failures, error)

    assert health(settings).last_error_cause is cause


@pytest.mark.parametrize(("error", "cause"), REAL_ERRORS)
def test_a_failing_mentions_search_names_its_cause_the_same_way(settings, error, cause):
    _failing(settings.mentions_failure, error)

    assert health(settings).mentions_error_cause is cause


def test_a_network_fault_carries_no_fix_even_from_a_record_that_kept_one(settings):
    _failing(settings.watcher_failures, 'Post "https://api.github.com/graphql": unexpected EOF',
             fix="Log in with `gh auth login`, then this page retries.")

    assert (health(settings).last_error_cause, health(settings).fix) == (Cause.NETWORK, None)


TELLING_NAMES = {"gh_account": "tls-timeout-bot",
                 "repos": (RepoEntry(Repo("acme", "request-timeout"), "/code/request-timeout"),
                           RepoEntry(Repo("acme", "rustls-bindings"), "/code/rustls-bindings"))}


@pytest.mark.parametrize("error", [
    "watcher cannot search acme/request-timeout, acme/rustls-bindings as tls-timeout-bot: "
    "gh search prs --repo=acme/request-timeout --repo=acme/rustls-bindings failed (exit 1): "
    "HTTP 401: Bad credentials (https://api.github.com/search/issues?q=repo%3Aacme%2Frequest-timeout)",
    "gh repo view acme/rustls-bindings --json nameWithOwner failed (exit 1): "
    "GraphQL: Could not resolve to a Repository with the name 'acme/rustls-bindings'.",
    "git -C /code/request-timeout fetch failed: [Errno 28] No space left on device",
])
def test_a_fault_to_fix_is_not_taken_for_the_network_by_the_names_the_error_carries(
        tmp_path, error):
    named = fake_settings(tmp_path, **TELLING_NAMES)
    _failing(named.watcher_failures, error)

    assert health(named).last_error_cause is Cause.OPERATOR


def test_a_network_fault_still_reads_as_one_beside_names_that_look_like_one(tmp_path):
    named = fake_settings(tmp_path, **TELLING_NAMES)
    _failing(named.watcher_failures,
             "watcher cannot search acme/request-timeout as tls-timeout-bot: "
             'Post "https://api.github.com/graphql": net/http: TLS handshake timeout')

    assert health(named).last_error_cause is Cause.NETWORK


def test_a_poll_that_is_not_failing_has_no_cause(settings):
    assert (health(settings).last_error_cause, health(settings).mentions_error_cause) == (
        None, None)
