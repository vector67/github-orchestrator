import json

import pytest

from github_orchestrator.domain import Cause
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


def test_a_poll_that_is_not_failing_has_no_cause(settings):
    assert (health(settings).last_error_cause, health(settings).mentions_error_cause) == (
        None, None)
